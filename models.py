from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
import datetime

db = SQLAlchemy()

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(50), nullable=False, default='proveedor')
    
    # Proveedor specific fields
    proveedor_id = db.Column(db.String(50), nullable=True)
    name = db.Column(db.String(150), nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    email = db.Column(db.String(150), nullable=True)
    address = db.Column(db.String(250), nullable=True)
    
    # First login flag - when True, user must complete profile
    first_login = db.Column(db.Boolean, default=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Shift(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('shifts', lazy=True))
    
    date_str = db.Column(db.String(20), nullable=False) # 'YYYY-MM-DD'
    time_str = db.Column(db.String(20), nullable=False) # 'HH:MM AM'
    
    planta = db.Column(db.String(100), nullable=False) # 'Barracas' or 'Pibera'
    oc_number = db.Column(db.String(50), nullable=False)
    articulo_id = db.Column(db.String(50), nullable=True)
    articulo_name = db.Column(db.String(250), nullable=True)
    
    pallets = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(50), nullable=False, default='Confirmado') # 'Confirmado' or 'Cancelado'
    
    # A shift booking can take multiple slots. 
    # This stores how many 'blocks' of 5 pallets this shift conceptually covers
    # for rendering purposes, or we just insert multiple Shift records.
    # It's better to insert multiple consecutive shifts. So each record is max 5.
    
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
class BlockedDay(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date_str = db.Column(db.String(20), unique=True, nullable=False) # 'YYYY-MM-DD'
    reason = db.Column(db.String(200), nullable=True) 
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
