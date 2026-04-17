from flask import Flask, jsonify, request
from flask_cors import CORS  
import firebase_admin
from firebase_admin import credentials, firestore
import os
from dotenv import load_dotenv
from auth import token_obrigatorio
from flasgger import Swagger
import json
import datetime
import jwt

load_dotenv()

# 1. Configuração do Firebase
if not firebase_admin._apps:
    if os.getenv('VERCEL'):
        # Certifique-se de que a variável FIREBASE_CREDENTIALS na Vercel seja o JSON completo
        cred_json = json.loads(os.getenv('FIREBASE_CREDENTIALS'))
        cred = credentials.Certificate(cred_json)
    else:
        cred = credentials.Certificate("firebase.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

# 2. Configuração do Flask
app = Flask(__name__)
CORS(app, origins="*")

app.config['SWAGGER'] = {
    'openapi': '3.0.3'
}
swagger = Swagger(app, template_file='openapi.yaml')

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

adm_usuario = os.getenv('adm_usuario')
adm_senha = os.getenv('adm_senha')

@app.route('/', methods=['GET'])
def root():
    return jsonify({
        'api': 'academia puxa ferro',
        'version': '1.0',
        'Author': 'Beatriz e Mayara',
        'Description': 'API da academia puxa ferro usando Flask e Firebase'
    }), 200

@app.route('/login', methods=['POST'])
def login():
    dados = request.get_json()
    if dados.get("usuario") == adm_usuario and dados.get("senha") == adm_senha:
        payload = {
            "usuario": adm_usuario,
            # Uso de timezone-aware datetime para evitar avisos de expiração
            "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=24)
        }
        token = jwt.encode(payload, app.config['SECRET_KEY'], algorithm="HS256")
        return jsonify({"token": token}), 200
   
    return jsonify({"erro": "Credenciais incorretas"}), 401

# ========================================================================
#   LISTAGEM DE ALUNOS
# ========================================================================
@app.route("/alunos", methods=['GET'])
@token_obrigatorio
def listar_alunos():
    try:
        alunos_ref = db.collection('alunos').get()
        lista = [doc.to_dict() for doc in alunos_ref]
        return jsonify(lista), 200
    except Exception as e:
        print(f"Erro ao listar: {e}")
        return jsonify({"erro": "Erro ao carregar lista de alunos"}), 500

# ========================================================================
#   CATRACA (ACESSO)
# ========================================================================
@app.route("/catraca", methods=['POST'])
def consultar_acesso():
    try:
        dados = request.get_json()
        if not dados or "cpf" not in dados:
            return jsonify({"erro": "CPF não informado"}), 400
           
        cpf_recebido = ''.join(filter(str.isdigit, str(dados.get("cpf"))))
        resultado_busca = db.collection('alunos').where('cpf', '==', cpf_recebido).limit(1).get()

        aluno_doc = None
        for item in resultado_busca:
            aluno_doc = item.to_dict()

        if not aluno_doc:
            return jsonify({"status": "BLOQUEADO", "mensagem": "CPF não cadastrado"}), 404

        status_aluno = aluno_doc.get("status", "").upper()
       
        if status_aluno == "ATIVO":
            return jsonify({
                "nome": aluno_doc.get("nome"),
                "status": "ATIVO",
                "mensagem": "Acesso Liberado!"
            }), 200
        else:
            return jsonify({
                "nome": aluno_doc.get("nome"),
                "status": "BLOQUEADO",
                "mensagem": f"Acesso negado. Status: {status_aluno}"
            }), 403

    except Exception as e:
        print(f"Erro na catraca: {e}")
        return jsonify({"status": "ERRO_SISTEMA", "mensagem": "Falha no banco de dados."}), 503

# ========================================================================
#   CADASTRO (POST) - Proteção contra duplicatas e Auto-ID
# ========================================================================
@app.route("/alunos", methods=['POST'])
@token_obrigatorio
def cadastrar_aluno():
    dados = request.get_json()
    if not dados or 'cpf' not in dados or 'nome' not in dados:
        return jsonify({"erro": "Dados incompletos."}), 400
   
    try:
        cpf_entrada = str(dados.get("cpf")).strip()
        cpf_limpo = ''.join(filter(str.isdigit, cpf_entrada))

        if len(cpf_limpo) != 11:
            return jsonify({"erro": "CPF deve conter 11 números."}), 400

        # Verifica se CPF já existe
        existente = db.collection('alunos').where('cpf', '==', cpf_limpo).get()
        if len(existente) > 0:
            return jsonify({"erro": "Este CPF já está cadastrado no sistema."}), 409

        # Lógica de ID Incremental
        contador_ref = db.collection('contador').document('controle_de_id')
        contador_doc = contador_ref.get()
       
        ultimo_id = contador_doc.to_dict().get('ultimo_id', 0) if contador_doc.exists else 0
        novo_id = ultimo_id + 1
        contador_ref.set({'ultimo_id': novo_id})

        db.collection('alunos').add({
            "id": int(novo_id),
            "nome": str(dados.get("nome")).strip(),
            "cpf": cpf_limpo,
            "status": str(dados.get("status", "ATIVO")).upper()
        })
        return jsonify({"mensagem": "Aluno salvo com sucesso!", "id": novo_id}), 201

    except Exception as e:
        print(f"Erro no POST alunos: {e}")
        return jsonify({"erro": "Erro interno ao cadastrar aluno"}), 500

# ========================================================================
#   EDIÇÃO TOTAL (PUT)
# ========================================================================
@app.route("/alunos/<int:id>", methods=['PUT'])
@token_obrigatorio
def atualizar_aluno_total(id):
    dados = request.get_json()
    try:
        cpf_novo = ''.join(filter(str.isdigit, str(dados.get("cpf"))))
       
        # 1. Busca o aluno pelo campo 'id' numérico
        docs = db.collection('alunos').where('id', '==', int(id)).limit(1).get()
        if not docs:
            return jsonify({"erro": "Aluno não encontrado"}), 404
       
        aluno_atual_ref = docs[0].reference

        # 2. Verifica se o novo CPF já pertence a OUTRO aluno
        outros_com_mesmo_cpf = db.collection('alunos').where('cpf', '==', cpf_novo).get()
        for doc in outros_com_mesmo_cpf:
            if doc.to_dict().get('id') != int(id):
                return jsonify({"erro": "Já existe outro aluno com este CPF."}), 409

        # 3. Atualiza
        aluno_atual_ref.update({
            "nome": str(dados.get("nome")).strip(),
            "cpf": cpf_novo,
            "status": str(dados.get("status")).upper()
        })
        return jsonify({"mensagem": "Aluno atualizado com sucesso!"}), 200

    except Exception as e:
        print(f"Erro no PUT alunos: {e}")
        return jsonify({"erro": "Erro ao atualizar registro"}), 500

# ========================================================================
#   EXCLUIR (DELETE)
# ========================================================================
@app.route("/alunos/deletar", methods=['DELETE'])
@token_obrigatorio
def deletar_aluno():
    try:
        dados = request.get_json()
        cpf_para_excluir = dados.get("cpf")
        if not cpf_para_excluir:
            return jsonify({"erro": "CPF não informado"}), 400

        busca = db.collection('alunos').where('cpf', '==', str(cpf_para_excluir)).get()

        achou = False
        for doc in busca:
            doc.reference.delete()
            achou = True

        if not achou:
            return jsonify({"erro": "Aluno não encontrado para exclusão"}), 404

        return jsonify({"mensagem": "Excluído com sucesso!"}), 200
    except Exception as e:
        print(f"Erro no DELETE: {e}")
        return jsonify({"erro": "Erro ao deletar aluno"}), 500

# ========================================================================
#   TRATAMENTO DE ERROS
# ========================================================================
@app.errorhandler(500)
def erro_interno(e):
    return jsonify({
        "status": "OFFLINE",
        "erro": "Erro interno no servidor.",
        "mensagem": "Verifique os logs do Firebase/Vercel."
    }), 500

if __name__ == '__main__':
    # Rodar localmente
    app.run(debug=True)


