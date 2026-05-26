-- Petclinic Oracle DDL (PR A integration fixture)
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

CREATE TABLE visits (
    id NUMBER(10) PRIMARY KEY,
    pet_id NUMBER(10) NOT NULL,
    visit_date DATE NOT NULL,
    description CLOB,
    amount NUMBER(38, 10),
    CONSTRAINT fk_visits_pets FOREIGN KEY (pet_id) REFERENCES pets(id)
);

CREATE TABLE vets (
    id NUMBER(10) PRIMARY KEY,
    first_name VARCHAR2(50) NOT NULL,
    last_name VARCHAR2(50) NOT NULL
);

CREATE SEQUENCE owners_seq;
