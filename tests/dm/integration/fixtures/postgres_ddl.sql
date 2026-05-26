-- Petclinic PostgreSQL target DDL (PR A integration fixture).
-- OMNIX-generated equivalent of oracle_ddl.sql, with TZ-aware timestamps and
-- explicit precision/scale where Oracle was generous.
CREATE TABLE owner (
    id SERIAL PRIMARY KEY,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL,
    email VARCHAR(255) UNIQUE,
    address TEXT,
    city VARCHAR(80),
    telephone VARCHAR(20),
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE pet (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    birth_date DATE,
    owner_id INTEGER NOT NULL,
    CONSTRAINT fk_pet_owner FOREIGN KEY (owner_id) REFERENCES owner(id) ON DELETE CASCADE
);

CREATE TABLE visit (
    id SERIAL PRIMARY KEY,
    pet_id INTEGER NOT NULL,
    visit_date TIMESTAMPTZ NOT NULL,
    description TEXT,
    amount NUMERIC(10, 2),
    CONSTRAINT fk_visit_pet FOREIGN KEY (pet_id) REFERENCES pet(id) ON DELETE CASCADE
);

CREATE TABLE vet (
    id SERIAL PRIMARY KEY,
    first_name VARCHAR(50) NOT NULL,
    last_name VARCHAR(50) NOT NULL
);
