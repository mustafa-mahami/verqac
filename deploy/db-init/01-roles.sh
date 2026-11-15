#!/bin/sh
# Runs once, when the database volume is first created.
# verqac_owner owns the schema and runs migrations; verqac_app is what the API uses (RLS applies to it).
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<SQL
CREATE ROLE verqac_owner LOGIN PASSWORD '${VERQAC_OWNER_PASSWORD}';
CREATE ROLE verqac_app LOGIN PASSWORD '${VERQAC_APP_PASSWORD}';
CREATE DATABASE verqac OWNER verqac_owner;
REVOKE ALL ON DATABASE verqac FROM PUBLIC;
GRANT CONNECT ON DATABASE verqac TO verqac_app;
SQL
