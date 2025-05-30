from peewee import Model, SqliteDatabase, FloatField, DateTimeField, UUIDField
from datetime import datetime
from uuid import uuid4

db = SqliteDatabase('sensores.db')

class BaseModel(Model):
    class Meta:
        database = db

class Lectura(BaseModel):
    id = UUIDField(primary_key=True, default=uuid4)
    timestamp = DateTimeField(default=datetime.now)
    od = FloatField(null=True)
    ph = FloatField(null=True)
    con = FloatField(null=True)
    tur = FloatField(null=True)
    tsd = FloatField(null=True)
    tem = FloatField(null=True)

def init_db():
    db.connect()
    db.create_tables([Lectura], safe=True)
    db.close()

def guardar_lectura(data):
    Lectura.create(**data)
