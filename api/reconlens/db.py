import psycopg
from pgvector.psycopg import register_vector

from reconlens import config


def connect() -> psycopg.Connection:
    conn = psycopg.connect(config.database_url())
    register_vector(conn)
    return conn
