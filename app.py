from flask import Flask, request, jsonify, session
from flask_restx import Api, Resource, fields
from flask_cors import CORS  # Importa CORS
import firebase_admin
from firebase_admin import credentials, firestore, auth, storage
from werkzeug.utils import secure_filename
import logging

#Inicializar la app de Flask
app = Flask(__name__)
app.secret_key = '121003'

# Configurar CORS
CORS(app, resources={r"/*": {"origins": "http://localhost:3000", "supports_credentials": True}})

#Inicializar API con Flask-RESTX
api = Api(app, version='1.0', title='Bienes Raices API', 
          description='API para gestionar bienes raíces, usuarios y boletas', 
          doc='/swagger/') #Ruta para la documentación de Swagger

#Inicializar Firebase

cred = credentials.Certificate('config/bienesraicesapp-2082b-firebase-adminsdk-ouekj-8cc7711eb0.json')
firebase_admin.initialize_app(cred, {'storageBucket':'firebase-adminsdk-ouekj@bienesraicesapp-2082b.iam.gserviceaccount.com'})

#Inicializar Firestore
db = firestore.client()
bucket = storage.bucket()
# Configuración de logging
logging.basicConfig(level=logging.DEBUG)

#Modelos para Swagger
bien_raiz_model = api.model('BienRaiz', {
    'nombre': fields.String(required=True, description = 'Nombre del bien raíz'),
    'precio':fields.Float(required=True, description = 'Precio del bien raíz'),
    'ubicacion': fields.String(required=True, description='Ubicación del bien raíz'),
    'descripcion': fields.String(required=True, description='Descripción del bien raíz'),  # Nueva descripción
    'habitaciones': fields.Integer(required=True, description='Cantidad de habitaciones'),  # Nueva propiedad
    'banos': fields.Integer(required=True, description='Cantidad de baños'),  # Nueva propiedad
    'imagen_url': fields.String(description='URL de la imagen del bien raíz')  # Campo existente
})

boleta_model = api.model('Boleta', {
    'boleta': fields.String(required = True, description='Archivo de la boleta')
})
subir_boleta_model = api.parser()
subir_boleta_model.add_argument('boleta', location='files', type='file', required=True, help='Archivo de la boleta a subir')
# Recursos de la API
@api.route('/login')
class Login(Resource):
    @api.doc(description="Iniciar sesión con email y contraseña")
    @api.expect(api.model('Login', {
        'email': fields.String(required=True, description='Correo Electrónico del usuario'),
        'password': fields.String(required=True, description='Contraseña del usuario'),
    }))
    def post(self):
        email = request.json.get('email')
        password = request.json.get('password')
        try:
            user = auth.get_user_by_email(email)
            # Aquí podrías implementar la validación de la contraseña si es necesario
            session['user_id'] = user.uid

            user_data = db.collection('user').document(user.uid).get()

            if user_data.exists:
                user_info = user_data.to_dict()
                nombre_completo = user_info.get('nombre_completo')
                tipo_usuario = user_info.get('tipo_usuario')
                return{"message": "Inicio de sesion exitoso", "email": email,"nombre_completo":nombre_completo ,"tipo_usuario":tipo_usuario}, 201
            else:
                return {"error": "El usuario no tiene datos adicionales"}, 404
        except Exception as e:
            return {"error": str(e)}, 401

@api.route('/signup')
class Signup(Resource):
    @api.doc(description="Registrarse con email, contraseña y tipo de usuario")
    @api.expect(api.model('Signup', {
        'email': fields.String(required=True, description='Correo Electrónico del usuario'),
        'password': fields.String(required=True, description='Contraseña del usuario'),
        'nombre_completo': fields.String(required=True, description='Nombre completo del usuario'),
        'tipo_usuario': fields.String(required=True, description='Tipo de usuario vendedor o comprador')
    }))
    def post(self):
        email = request.json.get('email')
        password = request.json.get('password')
        nombre_completo = request.json.get('nombre_completo')
        tipo_usuario = request.json.get('tipo_usuario')

        if tipo_usuario not in ['vendedor', 'comprador']:
            return {"error": "El tipo de usuario debe ser 'vendedor' o 'comprador'"}, 400
        try:
            user = auth.create_user(email=email, password=password)

            db.collection('user').document(user.uid).set({
                'email':email,
                'nombre_completo': nombre_completo,
                'tipo_usuario':tipo_usuario
            })
            session['user_id'] = user.uid
            return {"message": "Registro exitoso", "tipo_usuario": tipo_usuario}, 201
        except Exception as e:
            return {"error": str(e)}, 400

@api.route('/bienes_raices')
class BienesRaices(Resource):
    @api.marshal_list_with(bien_raiz_model)
    @api.doc(description="Obtener todos los bienes raíces")
    def get(self):
        bienes_raices = []
        docs = db.collection('bienes_raices').stream()

        for doc in docs:
            bien = doc.to_dict()
            bien['id'] = doc.id
            bienes_raices.append(bien)
        return bienes_raices, 200
    
    @api.expect(bien_raiz_model)
    @api.doc(description="Agregar un nuevo bien raíz")
    def post(self):
        data = request.json
        nombre = data.get('nombre')
        precio = data.get('precio')
        ubicacion = data.get('ubicacion')
        descripcion = data.get('descripcion')  # Nueva propiedad
        habitaciones = int(data.get('habitaciones'))  # Nueva propiedad
        banos = int(data.get('banos'))  # Nueva propiedad

        #Verifica si se proporcionó una imagen
        if 'imagen' not in request.files:
            return {"message":"No se ha proporcionado ninguna imagen"}, 400
        
        imagen = request.file['imagen']
        filename = secure_filename(imagen.filename)

        # Sube la imagen a Firebase Storage
        blob = bucket.blob(f'bienes_raices/{filename}')
        blob.upload_from_file(imagen, content_type=imagen.content_type)

        # Obtén la URL pública de la imagen
        imagen_url = blob.public_url

        doc_ref = db.collection('bienes_raices').add({
            'nombre': nombre,
            'precio': precio,
            'ubicacion': ubicacion,
            'descripcion': descripcion,  # Guardar la descripción
            'habitaciones': habitaciones,  # Guardar cantidad de habitaciones
            'banos': banos,  # Guardar cantidad de baños
            'imagen_url': imagen_url  # URL de la imagen
        })
        return {"message": "Bien raíz agregado", "id": doc_ref[1].id}, 201

@api.route('/bienes_raices/<id>')
class BienRaizDetail(Resource):
    @api.expect(bien_raiz_model)
    @api.doc(description="Actualizar un bien raíz por ID")
    def put(self, id):
        data = request.json
        doc_ref = db.collection('bienes_raices').document(id)
        doc_ref.update({
            'nombre': data.get('nombre'),
            'precio': data.get('precio'),
            'ubicacion': data.get('ubicacion')
        })
        return {"message": "Bien raíz actualizado"}, 200
    
    @api.doc(description="Eliminar un bien raíz por ID")
    def delete(self, id):
        db.collection('bienes_raices').document(id).delete()
        return {"message": "Bien raíz eliminado"}, 200

@api.route('/subir_boleta')
class Boletas(Resource):
    @api.expect(subir_boleta_model)
    @api.doc(description="Subir una boleta en formato PDF")
    def post(self):
        args = subir_boleta_model.parse_args()
        file = args.get('boleta')

        if file is None:
            return {"message": "No se ha proporcionado ningún archivo"}, 400

        filename = secure_filename(file.filename)
        blob = bucket.blob(f'boletas/{filename}')

        # Subir el archivo
        blob.upload_from_file(file, content_type=file.content_type)

        # Guardar información de la boleta en Firestore
        db.collection('boletas').add({
            'filename': filename,
            'url': blob.public_url,  # O usa blob.generate_signed_url(expiration=3600) si necesitas una URL firmada
            'uploaded_at': firestore.SERVER_TIMESTAMP
        })

        return {"message": f"Boleta {filename} subida exitosamente"}, 201

@api.route('/descargar_boletas/<string:filename>')
class DescargarBoleta(Resource):
    @api.doc(description="Descargar una boleta por nombre de archivo")
    def get(self, filename):
        blob = bucket.blob(f'boletas/{filename}')

        if not blob.exists():
            return {"message": "La boleta no existe"}, 404
        
        url = blob.generate_signed_url(expiration=3600)

        return {"url": url}, 200

if __name__ == '__main__':
    app.run(debug=True)