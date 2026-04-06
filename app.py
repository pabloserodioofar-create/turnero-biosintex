import os
import random
import string
import datetime

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user

from models import db, User, Shift, BlockedDay
from excel_service import get_oc_details_list, get_supplier_info, get_turnos_df, normalize_planta, get_excel_last_modified
from werkzeug.utils import secure_filename

# Días feriados de ejemplo (Argentina)
FERIADOS_2026 = ['2026-01-01', '2026-02-16', '2026-02-17', '2026-03-24', '2026-04-02', '2026-04-03', '2026-05-01', '2026-05-25', '2026-06-20', '2026-07-09', '2026-12-08', '2026-12-25']

def is_business_day(d):
    if d.weekday() >= 5: # Lunes=0, Domingo=6
        return False
    if d.strftime('%Y-%m-%d') in FERIADOS_2026:
        return False
    return True

import logging
logging.basicConfig(filename='flask_errors.log', level=logging.DEBUG)

def get_first_available_date():
    current = datetime.date.today()
    business_days_passed = 0
    while business_days_passed < 2:
        current += datetime.timedelta(days=1)
        if is_business_day(current):
            business_days_passed += 1
    return current.strftime('%Y-%m-%d')

def generate_random_password(length=8):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

def sync_proveedores_from_excel():
    df = get_turnos_df()
    if df.empty:
        return []
    
    prov_col = next((c for c in df.columns if 'Proveedor' in str(c) and 'Nombre' not in str(c) and 'Codigo' not in str(c)), None)
    name_col = next((c for c in df.columns if 'Nombre_2' in str(c)), None)
    
    if not prov_col:
        return []
    
    proveedores_en_excel = df[prov_col].dropna().unique()
    nuevos_proveedores = []
    
    for prov_id in proveedores_en_excel:
        prov_id_str = str(int(prov_id)) if isinstance(prov_id, float) else str(prov_id)
        
        existing = User.query.filter_by(proveedor_id=prov_id_str, role='proveedor').first()
        if not existing:
            name = ""
            if name_col:
                name_match = df[df[prov_col].astype(str) == prov_id_str]
                if not name_match.empty:
                    name = str(name_match.iloc[0][name_col])
            
            password = generate_random_password()
            new_user = User(
                username=prov_id_str,
                role='proveedor',
                proveedor_id=prov_id_str,
                name=name,
                first_login=True
            )
            new_user.set_password(password)
            db.session.add(new_user)
            
            nuevos_proveedores.append({
                'proveedor_id': prov_id_str,
                'name': name,
                'password': password
            })
    
    if nuevos_proveedores:
        db.session.commit()
        print("\n=== NUEVOS PROVEEDORES CREADOS ===")
        for p in nuevos_proveedores:
            print(f"Proveedor: {p['proveedor_id']} | Nombre: {p['name']} | Password: {p['password']}")
        print("==================================\n")
    
    return nuevos_proveedores

app = Flask(__name__)
app.config['SECRET_KEY'] = 'biosintex_super_secret'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///turneros_v2.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
    db.create_all()
    if not User.query.filter_by(role='supervisor').first():
        sup = User(username='admin@biosintex.com', role='supervisor', name='Supervisor Biosintex')
        sup.set_password('admin123')
        db.session.add(sup)
        db.session.commit()
    
    sync_proveedores_from_excel()

@app.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.role == 'supervisor':
            return redirect(url_for('supervisor_dashboard'))
        else:
            return redirect(url_for('proveedor_dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            if user.role == 'supervisor':
                return redirect(url_for('supervisor_dashboard'))
            elif user.first_login:
                return redirect(url_for('complete_profile'))
            return redirect(url_for('proveedor_dashboard'))
        else:
            flash('Usuario o contraseña incorrectos', 'danger')
            return redirect(url_for('login'))
            
    return render_template('login.html', type='login')

@app.route('/completar-perfil', methods=['GET', 'POST'])
@login_required
def complete_profile():
    if current_user.role != 'proveedor':
        return redirect(url_for('index'))
    
    if not current_user.first_login:
        return redirect(url_for('proveedor_dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        phone = request.form.get('phone')
        
        current_user.email = email
        current_user.phone = phone
        current_user.first_login = False
        db.session.commit()
        
        flash('Perfil completado exitosamente', 'success')
        return redirect(url_for('proveedor_dashboard'))
    
    return render_template('complete_profile.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/proveedor')
@login_required
def proveedor_dashboard():
    if current_user.role != 'proveedor':
        return redirect(url_for('index'))
    blocked = BlockedDay.query.all()
    blocked_dates = [b.date_str for b in blocked]
    return render_template('proveedor.html', 
        proveedor_id=current_user.proveedor_id,
        min_date=get_first_available_date(),
        feriados=FERIADOS_2026,
        blocked_days=blocked_dates
    )

@app.route('/api/check_oc', methods=['POST'])
@login_required
def check_oc():
    if current_user.role != 'proveedor':
        return jsonify({'error': 'Unauthorized'}), 403
        
    data = request.json
    oc_number = data.get('oc')
    proveedor_id = current_user.proveedor_id
    
    matches = get_oc_details_list(proveedor_id, oc_number)
    
    if len(matches) == 1:
        return jsonify(matches[0])
    elif len(matches) > 1:
        return jsonify({'options': matches})
    else:
        return jsonify({'error': 'Orden de compra no encontrada o no pertenece a su número de proveedor.'}), 404

def generate_time_slots():
    slots = []
    for h in range(7, 13):
        slots.append(f"{h:02d}:00")
    return slots

@app.route('/api/available_slots', methods=['GET'])
@login_required
def available_slots():
    try:
        date_str = request.args.get('date') 
        planta = request.args.get('planta')
        pallets_str = request.args.get('pallets', '1')
        
        print(f"DEBUG: available_slots called with date={date_str}, planta={planta}, pallets={pallets_str}")
        
        if not pallets_str:
            pallets_str = '1'
        pallets = int(pallets_str)
        
        required_blocks = (pallets + 4) // 5 
        
        all_slots = generate_time_slots()
        
        # Filtro de planta opcional pero recomendado
        query = Shift.query.filter_by(date_str=date_str, status='Confirmado')
        if planta and str(planta).lower() not in ["undefined", "null", "nan", "none", ""]:
            query = query.filter_by(planta=planta)
            
        try:
            booked = query.all()
        except Exception as db_err:
            print(f"Database error: {db_err}")
            booked = [] 
            
        # Check if day is blocked by supervisor
        if BlockedDay.query.filter_by(date_str=date_str).first():
            return jsonify({'available': [], 'required': required_blocks, 'blocked': True})
            
        booked_times = [s.time_str for s in booked]
        
        available = []
        for i in range(len(all_slots)):
            # No permitir empezar un turno largo a las 12 (solo dura 1h el periodo)
            if required_blocks > 1 and all_slots[i] == '12:00':
                continue
                
            can_fit = True
            for j in range(required_blocks):
                if i + j >= len(all_slots):
                    can_fit = False
                    break
                if all_slots[i+j] in booked_times:
                    can_fit = False
                    break
                    
            if can_fit:
                available.append(all_slots[i])
                
        return jsonify({'available': available, 'required': required_blocks})
    except Exception as e:
        import traceback
        error_msg = f"Error in available_slots: {str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500

@app.route('/api/book_shift', methods=['POST'])
@login_required
def book_shift():
    if current_user.role != 'proveedor':
        return jsonify({'error': 'Unauthorized'}), 403
        
    data = request.json
    date_str = data.get('date')
    start_time = data.get('time')
    planta = data.get('planta')
    oc_number = data.get('oc')
    pallets = int(data.get('pallets', 1))
    
    required_blocks = (pallets + 4) // 5
    all_slots = generate_time_slots()
    
    try:
        start_idx = all_slots.index(start_time)
    except ValueError:
        return jsonify({'error': 'Hora inválida'}), 400
        
    if required_blocks > 1 and start_time == '12:00':
        return jsonify({'error': 'No hay suficientes turnos a las 12:00 para esta cantidad de pallets.'}), 400
        
    if start_idx + required_blocks > len(all_slots):
        return jsonify({'error': 'No hay suficientes turnos disponibles desde la hora seleccionada para esta cantidad de pallets.'}), 400
        
    matches = get_oc_details_list(current_user.proveedor_id, oc_number)
    details = next((m for m in matches if m['oc'] == oc_number), None)
    if not details:
        return jsonify({'error': 'OC inválida'}), 400

    # VALIDAR COLUMN Q: No permitir turnos antes del mes de entrega
    fecha_entrega_q = details.get('fecha_entrega_q', '')
    if fecha_entrega_q:
        try:
            parts = fecha_entrega_q.split('-')
            if len(parts) == 3:
                year = int(parts[0])
                month = int(parts[1])
                first_day_allowed = datetime.date(year, month, 1)
                
                requested_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
                
                if requested_date < first_day_allowed:
                    return jsonify({
                        'error': f'Por presupuesto, no se pueden agendar turnos antes de {first_day_allowed.strftime("%01m/%Y")}. La OC tiene fecha de entrega en {month}/{year}.'
                    }), 400
        except Exception as e:
            print(f"Error validating fecha_entrega_q: {e}")

    for j in range(required_blocks):
        t = all_slots[start_idx + j]
        if Shift.query.filter_by(date_str=date_str, time_str=t, planta=planta, status='Confirmado').first():
            return jsonify({'error': f'El turno block {t} ya se encuentra ocupado. Por favor seleccione otro.'}), 400

    pallets_rem = pallets
    for j in range(required_blocks):
        t = all_slots[start_idx + j]
        p_count = min(pallets_rem, 5)
        pallets_rem -= p_count
        
        shift = Shift(
            user_id=current_user.id,
            date_str=date_str,
            time_str=t,
            planta=normalize_planta(planta),
            oc_number=oc_number,
            articulo_id=details['articulo'],
            articulo_name=details['nombre_articulo'],
            pallets=p_count,
            status='Confirmado'
        )
        db.session.add(shift)
        
    db.session.commit()
    
    return jsonify({'success': True, 'msg': 'Turno reservado con éxito'})

@app.route('/supervisor')
@login_required
def supervisor_dashboard():
    if current_user.role != 'supervisor':
        return redirect(url_for('index'))
    return render_template('supervisor.html')

@app.route('/api/shifts', methods=['GET'])
@login_required
def get_shifts():
    if current_user.role != 'supervisor':
        return jsonify({'error': 'Unauthorized'}), 403
    
    start = request.args.get('start')
    end = request.args.get('end')
    
    query = Shift.query.filter_by(status='Confirmado')
    if start:
        query = query.filter(Shift.date_str >= start)
    if end:
        query = query.filter(Shift.date_str <= end)
        
    shifts = query.all()
    events = []
    
    # Group consecutive shifts by OC? Not strictly necessary, but FullCalendar manages events just fine.
    
    for s in shifts:
        events.append({
            'id': s.id,
            'title': f"{s.planta} - {s.user.name} ({s.pallets} Pallets) - OC: {s.oc_number}",
            'start': f"{s.date_str}T{s.time_str}:00",
            'end': f"{s.date_str}T{s.time_str[0:2]}:59:59",
            'planta': s.planta,
            'extendedProps': {
                'supplier': s.user.name,
                'supplier_email': s.user.username,
                'oc': s.oc_number,
                'articulo': s.articulo_name,
                'pallets': s.pallets,
                'time_str': s.time_str
            }
        })
    return jsonify(events)

@app.route('/api/cancel_shift', methods=['POST'])
@login_required
def cancel_shift():
    if current_user.role != 'supervisor':
        return jsonify({'error': 'Unauthorized'}), 403
        
    data = request.json
    shift_id = data.get('shift_id')
    reason = data.get('reason')
    
    shift = Shift.query.get(shift_id)
    if not shift:
        return jsonify({'error': 'Turno no encontrado'}), 404
        
    shifts_to_cancel = Shift.query.filter_by(
        date_str=shift.date_str, 
        planta=shift.planta, 
        oc_number=shift.oc_number, 
        user_id=shift.user_id,
        status='Confirmado'
    ).all()
    
    for s in shifts_to_cancel:
        s.status = 'Cancelado'
        
    db.session.commit()
    
    print("\n=== SIMULACIÓN DE ENVÍO DE EMAIL: CANCELACIÓN ===")
    print(f"Para: {shift.user.username}")
    print(f"Asunto: Cancelación de Turno en Planta {shift.planta}")
    print(f"Mensaje: Estimado {shift.user.name},")
    print(f"Su turno para la entrega de {shift.articulo_name} (OC: {shift.oc_number}) el día {shift.date_str} ha sido CANCELADO por el supervisor.")
    print(f"Motivo brindado: {reason}")
    print("Por favor, ingrese al portal y reprograme su turno de ser necesario.")
    print("===================================================\n")
    
    return jsonify({'success': True, 'msg': 'Turno cancelado con éxito y proveedor notificado.'})

@app.route('/api/excel_info', methods=['GET'])
@login_required
def get_excel_info():
    if current_user.role != 'supervisor':
        return jsonify({'error': 'Unauthorized'}), 403
    
    last_modified = get_excel_last_modified()
    df = get_turnos_df()
    
    return jsonify({
        'last_modified': last_modified,
        'total_ocs': len(df) if not df.empty else 0
    })

@app.route('/api/blocked_days', methods=['GET', 'POST'])
@login_required
def manage_blocked_days():
    if current_user.role != 'supervisor':
        return jsonify({'error': 'Unauthorized'}), 403
    
    if request.method == 'POST':
        data = request.json
        date_str = data.get('date')
        reason = data.get('reason', 'Bloqueado por supervisor')
        
        if not BlockedDay.query.filter_by(date_str=date_str).first():
            new_blocked = BlockedDay(date_str=date_str, reason=reason)
            db.session.add(new_blocked)
            db.session.commit()
            return jsonify({'success': True})
        return jsonify({'error': 'Día ya está bloqueado'}), 400
        
    blocked = BlockedDay.query.all()
    return jsonify([{'date': b.date_str, 'reason': b.reason, 'id': b.id} for b in blocked])

@app.route('/api/proveedores', methods=['GET'])
@login_required
def get_proveedores():
    if current_user.role != 'supervisor':
        return jsonify({'error': 'Unauthorized'}), 403
    
    proveedores = User.query.filter_by(role='proveedor').all()
    result = []
    for p in proveedores:
        result.append({
            'id': p.id,
            'proveedor_id': p.proveedor_id,
            'name': p.name,
            'email': p.email,
            'phone': p.phone,
            'first_login': p.first_login,
            'created_at': p.id
        })
    return jsonify(result)

@app.route('/api/reset_password/<int:user_id>', methods=['POST'])
@login_required
def reset_proveedor_password(user_id):
    if current_user.role != 'supervisor':
        return jsonify({'error': 'Unauthorized'}), 403
    
    user = User.query.get(user_id)
    if not user or user.role != 'proveedor':
        return jsonify({'error': 'Proveedor no encontrado'}), 404
    
    new_password = generate_random_password()
    user.set_password(new_password)
    user.first_login = True
    db.session.commit()
    
    print(f"\n=== NUEVA CONTRASEÑA PARA PROVEEDOR {user.proveedor_id} ===")
    print(f"Proveedor: {user.name}")
    print(f"Contraseña: {new_password}")
    print("======================================================\n")
    
    return jsonify({
        'success': True, 
        'proveedor_id': user.proveedor_id,
        'password': new_password
    })

@app.route('/api/sync_proveedores', methods=['POST'])
@login_required
def api_sync_proveedores():
    if current_user.role != 'supervisor':
        return jsonify({'error': 'Unauthorized'}), 403
    
    nuevos = sync_proveedores_from_excel()
    return jsonify({
        'success': True,
        'nuevos': len(nuevos),
        'details': nuevos
    })

@app.route('/api/unblock_day/<int:day_id>', methods=['DELETE', 'POST'])
@login_required
def unblock_day(day_id):
    if current_user.role != 'supervisor':
        return jsonify({'error': 'Unauthorized'}), 403
    
    day = BlockedDay.query.get(day_id)
    if day:
        db.session.delete(day)
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'error': 'No encontrado'}), 404

ALLOWED_EXTENSIONS = {'xlsx', 'xls'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/api/upload_excel', methods=['POST'])
@login_required
def upload_excel():
    if current_user.role != 'supervisor':
        return jsonify({'error': 'Unauthorized'}), 403
    
    if 'file' not in request.files:
        return jsonify({'error': 'No se encontró archivo'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'No se seleccionó archivo'}), 400
    
    if file and allowed_file(file.filename):
        filename = 'Turnos.xlsx'
        filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
        file.save(filepath)
        
        nuevos = sync_proveedores_from_excel()
        
        return jsonify({
            'success': True,
            'message': 'Archivo actualizado',
            'nuevos_proveedores': len(nuevos)
        })
    
    return jsonify({'error': 'Tipo de archivo no permitido'}), 400

@app.errorhandler(500)
def handle_500(e):
    import traceback
    error_msg = traceback.format_exc()
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Internal Server Error', 'traceback': error_msg}), 500
    return "<pre>" + error_msg + "</pre>", 500

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
