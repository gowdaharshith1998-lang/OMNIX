"""Shared fixtures for OMNIX-DM PR A tests."""

from __future__ import annotations

import pytest

PETCLINIC_PG_DDL = """
CREATE TABLE owner (
    id SERIAL PRIMARY KEY,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    email VARCHAR(255) UNIQUE,
    address TEXT,
    city VARCHAR(80),
    telephone VARCHAR(20),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE pet (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    birth_date DATE,
    owner_id INTEGER NOT NULL,
    type_id INTEGER NOT NULL,
    CONSTRAINT fk_pet_owner FOREIGN KEY (owner_id) REFERENCES owner(id) ON DELETE CASCADE
);

CREATE TABLE visit (
    id SERIAL PRIMARY KEY,
    pet_id INTEGER NOT NULL,
    visit_date TIMESTAMPTZ NOT NULL,
    description TEXT,
    CONSTRAINT fk_visit_pet FOREIGN KEY (pet_id) REFERENCES pet(id) ON DELETE CASCADE
);

CREATE INDEX idx_pet_owner ON pet(owner_id);
COMMENT ON COLUMN owner.email IS 'unique email address';
"""


PETCLINIC_ORACLE_DDL = """
CREATE TABLE owners (
    id NUMBER(10) PRIMARY KEY,
    first_name VARCHAR2(50) NOT NULL,
    last_name VARCHAR2(50) NOT NULL,
    email VARCHAR2(255),
    address CLOB,
    city VARCHAR2(80),
    telephone VARCHAR2(20),
    created_at DATE NOT NULL
);

CREATE TABLE pets (
    id NUMBER(10) PRIMARY KEY,
    name VARCHAR2(50) NOT NULL,
    birth_date DATE,
    owner_id NUMBER(10) NOT NULL,
    CONSTRAINT fk_pets_owners FOREIGN KEY (owner_id) REFERENCES owners(id)
);

CREATE SEQUENCE owners_seq;
"""


PETCLINIC_MYSQL_DDL = """
CREATE TABLE `owner` (
  `id` INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  `first_name` VARCHAR(50) NOT NULL,
  `last_name` VARCHAR(50) NOT NULL,
  `email` VARCHAR(255) UNIQUE,
  `address` TEXT,
  `city` VARCHAR(80) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci,
  `telephone` VARCHAR(20),
  `created_at` DATETIME NOT NULL
) ENGINE=InnoDB;
"""


PETCLINIC_MONGO_SCHEMA = """{
  "collections": {
    "owner": {
      "$jsonSchema": {
        "bsonType": "object",
        "required": ["_id", "first_name", "last_name"],
        "properties": {
          "_id": {"bsonType": "objectId"},
          "first_name": {"bsonType": "string"},
          "last_name": {"bsonType": "string"},
          "email": {"bsonType": ["string", "null"]},
          "address": {
            "bsonType": "object",
            "properties": {
              "city": {"bsonType": "string"},
              "zip": {"bsonType": "string"}
            }
          },
          "pets": {"bsonType": "array", "items": {"bsonType": "string"}}
        }
      }
    },
    "visit": {
      "$jsonSchema": {
        "bsonType": "object",
        "required": ["_id", "pet_id", "visit_date"],
        "properties": {
          "_id": {"bsonType": "objectId"},
          "pet_id": {"bsonType": "objectId"},
          "visit_date": {"bsonType": "date"},
          "description": {"bsonType": ["string", "null"]}
        }
      }
    }
  }
}"""


@pytest.fixture
def petclinic_pg_ddl() -> str:
    return PETCLINIC_PG_DDL


@pytest.fixture
def petclinic_oracle_ddl() -> str:
    return PETCLINIC_ORACLE_DDL


@pytest.fixture
def petclinic_mysql_ddl() -> str:
    return PETCLINIC_MYSQL_DDL


@pytest.fixture
def petclinic_mongo_schema() -> str:
    return PETCLINIC_MONGO_SCHEMA
