import datetime
import json
import random
import string
import sys
from datetime import timedelta
from pathlib import Path
from typing import List, Tuple

import mysql.connector
from mysql.connector import Error
import pytz

support_file_path_prefix = "/connector/integration_tests"
catalog_write_file = support_file_path_prefix + "/temp/configured_catalog_copy.json"
catalog_source_file = support_file_path_prefix + "/configured_catalog_template.json"
catalog_incremental_write_file = support_file_path_prefix + "/temp/incremental_configured_catalog_copy.json"
catalog_incremental_source_file = support_file_path_prefix + "/incremental_configured_catalog_template.json"
abnormal_state_write_file = support_file_path_prefix + "/temp/abnormal_state_copy.json"
abnormal_state_file = support_file_path_prefix + "/abnormal_state_template.json"

secret_config_file = '/connector/secrets/cat-config.json'
secret_active_config_file = support_file_path_prefix + '/temp/config_active.json'
secret_config_cdc_file = '/connector/secrets/cat-config-cdc.json'
secret_active_config_cdc_file = support_file_path_prefix + '/temp/config_cdc_active.json'

la_timezone = pytz.timezone('America/Los_Angeles')

def connect_to_db():
    with open(secret_config_file) as f:
        secret = json.load(f)

    try:
        conn = mysql.connector.connect(
            database=None,
            user=secret["username"],
            password=secret["password"],
            host=secret["host"],
            port=secret["port"]
        )
        print("Connected to the database successfully")
        return conn
    except Error as error:
        print(f"Error connecting to the database: {error}")
        sys.exit(1)

def insert_records(conn, schema_name: str, table_name: str, records: List[Tuple[str, str]]) -> None:
    try:
        cursor = conn.cursor()
        insert_query = f"INSERT INTO {schema_name}.{table_name} (id, name) VALUES (%s, %s) ON DUPLICATE KEY UPDATE id=id"

        for record in records:
            cursor.execute(insert_query, record)

        conn.commit()
        print("Records inserted successfully")
    except Error as error:
        print(f"Error inserting records: {error}")
        conn.rollback()
    finally:
        cursor.close()

def create_schema(conn, schema_name: str) -> None:
    try:
        cursor = conn.cursor()
        create_schema_query = f"CREATE DATABASE IF NOT EXISTS {schema_name}"
        cursor.execute(create_schema_query)
        conn.commit()
        print(f"Database '{schema_name}' created successfully")
    except Error as error:
        print(f"Error creating database: {error}")
        conn.rollback()
    finally:
        cursor.close()

def write_supporting_file(schema_name: str) -> None:
    print(f"writing schema name to files: {schema_name}")
    Path(support_file_path_prefix + "/temp").mkdir(parents=False, exist_ok=True)

    with open(catalog_write_file, "w") as file:
        with open(catalog_source_file, 'r') as source_file:
            file.write(source_file.read() % schema_name)
    with open(catalog_incremental_write_file, "w") as file:
        with open(catalog_incremental_source_file, 'r') as source_file:
            file.write(source_file.read() % schema_name)
    with open(abnormal_state_write_file, "w") as file:
        with open(abnormal_state_file, 'r') as source_file:
            file.write(source_file.read() % (schema_name, schema_name))

    with open(secret_config_file) as base_config:
        secret = json.load(base_config)
        secret["database"] = schema_name
        with open(secret_active_config_file, 'w') as f:
            json.dump(secret, f)

    with open(secret_config_cdc_file) as base_config:
        secret = json.load(base_config)
        secret["database"] = schema_name
        with open(secret_active_config_cdc_file, 'w') as f:
            json.dump(secret, f)

def create_table(conn, schema_name: str, table_name: str) -> None:
    try:
        cursor = conn.cursor()
        create_table_query = f"""
            CREATE TABLE IF NOT EXISTS {schema_name}.{table_name} (
                id VARCHAR(100) PRIMARY KEY,
                name VARCHAR(255) NOT NULL
            )
        """
        cursor.execute(create_table_query)
        conn.commit()
        print(f"Table '{schema_name}.{table_name}' created successfully")
    except Error as error:
        print(f"Error creating table: {error}")
        conn.rollback()
    finally:
        cursor.close()

def generate_schema_date_with_suffix() -> str:
    current_date = datetime.datetime.now(la_timezone).strftime("%Y%m%d")
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{current_date}_{suffix}"

def prepare() -> None:
    schema_name = generate_schema_date_with_suffix()
    print(f"schema_name: {schema_name}")
    with open("./generated_schema.txt", "w") as f:
        f.write(schema_name)

def cdc_insert():
    schema_name = load_schema_name_from_catalog()
    new_records = [
        ('4', 'four'),
        ('5', 'five')
    ]
    connection = connect_to_db()
    table_name = 'id_and_name_cat'
    if connection:
        insert_records(connection, schema_name, table_name, new_records)
        connection.close()

def setup():
    schema_name = load_schema_name_from_catalog()
    write_supporting_file(schema_name)
    table_name = "id_and_name_cat"

    records = [
        ('1', 'one'),
        ('2', 'two'),
        ('3', 'three')
    ]

    connection = connect_to_db()
    create_schema(connection, schema_name)
    create_table(connection, schema_name, table_name)
    insert_records(connection, schema_name, table_name, records)
    connection.close()

def load_schema_name_from_catalog():
    with open("./generated_schema.txt", "r") as f:
        return f.read()

def delete_schemas_with_prefix(conn, date_prefix):
    try:
        cursor = conn.cursor()

        query = f"""
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name LIKE '{date_prefix}%';
        """

        cursor.execute(query)
        schemas = cursor.fetchall()

        for schema in schemas:
            drop_query = f"DROP DATABASE IF EXISTS {schema[0]};"
            cursor.execute(drop_query)
            print(f"Database {schema[0]} has been dropped.")

        conn.commit()
    except Error as e:
        print(f"An error occurred: {e}")
        sys.exit(1)
    finally:
        cursor.close()

def teardown() -> None:
    conn = connect_to_db()
    today = datetime.datetime.now(la_timezone)
    yesterday = today - timedelta(days=1)
    formatted_yesterday = yesterday.strftime('%Y%m%d')
    delete_schemas_with_prefix(conn, formatted_yesterday)

def final_teardown() -> None:
    conn = connect_to_db()
    schema_name = load_schema_name_from_catalog()
    print(f"delete database {schema_name}")
    delete_schemas_with_prefix(conn, schema_name)

if __name__ == "__main__":
    command = sys.argv[1]
    if command == "setup":
        setup()
    elif command == "setup_cdc":
        setup()
    elif command == "teardown":
        teardown()
    elif command == "final_teardown":
        final_teardown()
    elif command == "prepare":
        prepare()
    elif command == "insert":
        cdc_insert()
    else:
        print(f"Unrecognized command {command}.")
        exit(1)
