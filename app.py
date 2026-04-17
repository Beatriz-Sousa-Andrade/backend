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
        cred = credentials.Certificate(json.loads(os.getenv('FIREBASE_CREDENTIALS')))
    else:
        cred = credentials.Certificate("firebase.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

# 2. Configuração do Flask
app = Flask(__name__)
CORS(app, origins="*")

app.config['SWAGGER']={
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
            "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        }
        token = jwt.encode(payload, app.config['SECRET_KEY'], algorithm="HS256")
        return jsonify({"token": token}), 200
   
    return jsonify({"erro": "Credenciais incorretas"}), 401

# ========================================================================
#   ROTA GET
# ========================================================================
@app.route("/alunos", methods=['GET'])
@token_obrigatorio
def listar_alunos():
    try:
        alunos_ref = db.collection('alunos').get()
        lista = [doc.to_dict() for doc in alunos_ref]
        return jsonify(lista), 200
    except Exception as e:
        return jsonify({"erro": f"Erro ao listar: {str(e)}"}), 500

# ========================================================================
#   APLICAÇÃO 1: CATRACA
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
        return jsonify({"status": "ERRO_SISTEMA", "mensagem": "Falha no banco de dados."}), 503

# ========================================================================
#   APLICAÇÃO 3: FRONTEND (CADASTRAR)
# ========================================================================
@app.route("/alunos", methods=['POST'])
@token_obrigatorio
def cadastrar_aluno():
    dados = request.get_json()
    if not dados or 'cpf' not in dados or 'nome' not in dados:
        return jsonify({"erro": "Dados incompletos."}), 400
   
    try:
        cpf_entrada = str(dados.get("cpf")).strip()
        
        # Bloqueia se houver letras
        if any(char.isalpha() for char in cpf_entrada):
            return jsonify({"erro": "CPF inválido. Não pode conter letras."}), 400

        # Limpa para ter apenas números (ex: 12345678901)
        cpf_limpo = ''.join(filter(str.isdigit, cpf_entrada))

        if len(cpf_limpo) != 11:
            return jsonify({"erro": "CPF deve conter 11 números."}), 400

        # --- LÓGICA DE UNICIDADE ---
        # Busca no Firestore se já existe algum documento com esse CPF exato
        conferir_cpf = db.collection('alunos').where('cpf', '==', cpf_limpo).get()
        
        if len(conferir_cpf) > 0:
            # Se encontrar algo, ele impede o cadastro. 
            # Se o aluno tivesse sido deletado antes, o 'len' seria 0 e ele passaria.
            return jsonify({
                "erro": "Este CPF já está cadastrado no sistema. Exclua o cadastro anterior para cadastrar novamente."
            }), 409 

        # --- PROSSEGUE COM O CADASTRO ---
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
        return jsonify({"erro": f"Erro interno: {str(e)}"}), 500

# ========================================================================
#   ATUALIZAÇÃO (PUT)
# ========================================================================
@app.route("/alunos/<int:id>", methods=['PUT'])
@token_obrigatorio
def atualizar_aluno_total(id):
    dados = request.get_json()
    try:
        cpf_limpo = ''.join(filter(str.isdigit, str(dados.get("cpf"))))
        docs = db.collection('alunos').where('id', '==', int(id)).get()

        if not docs:
            return jsonify({"erro": f"Aluno com ID {id} não encontrado"}), 404
       
        doc_ref = docs[0].reference
        doc_ref.update({
            "nome": str(dados.get("nome")).strip(),
            "cpf": cpf_limpo,
            "status": str(dados.get("status")).upper()
        })
        return jsonify({"mensagem": "Aluno atualizado!"}), 200
    except Exception as e:
        return jsonify({"erro": f"Erro interno: {str(e)}"}), 500

# ========================================================================
#   ATUALIZAÇÃO PARCIAL (PATCH)
# ========================================================================
@app.route("/alunos/<int:id>", methods=['PATCH'])
@token_obrigatorio
def atualizar_aluno_parcial(id):
    dados = request.get_json()
    try:
        docs = db.collection('alunos').where('id', '==', int(id)).limit(1).get()
        if not docs:
            return jsonify({"erro": "Aluno não encontrado"}), 404
       
        doc_ref = docs[0].reference
        update_aluno = {}
        if 'nome' in dados: update_aluno['nome'] = str(dados['nome']).strip()
        if 'cpf' in dados: update_aluno['cpf'] = ''.join(filter(str.isdigit, str(dados['cpf'])))
        if 'status' in dados: update_aluno['status'] = str(dados['status']).upper()
       
        doc_ref.update(update_aluno)
        return jsonify({"mensagem": "Sucesso no PATCH!"}), 200
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

# ========================================================================
#   EXCLUIR (DELETE)
# ========================================================================
@app.route("/alunos/deletar", methods=['DELETE'])
@token_obrigatorio
def deletar_aluno():
    dados = request.get_json()
    cpf_para_excluir = dados.get("cpf")
    busca = db.collection('alunos').where('cpf', '==', cpf_para_excluir).get()

    achou = False
    for doc in busca:
        doc.reference.delete()
        achou = True

    if not achou:
        return jsonify({"erro": "Não encontrado"}), 404

    return jsonify({"mensagem": "Excluído!"}), 200

# ========================================================================
#   ERROS CUSTOMIZADOS (ORIGINAIS)
# ========================================================================
@app.errorhandler(500)
def erro_interno(e):
    return jsonify({
        "status": "OFFLINE",
        "erro": "Erro interno no servidor ou banco de dados.",
        "mensagem": "Verifique o Firebase."
    }), 500

@app.errorhandler(Exception)
def lidar_com_excecao_generica(e):
    return jsonify({
        "status": "ERRO",
        "erro": str(e),
        "mensagem": "A requisição falhou."
    }), 500

if __name__ == '__main__':
    app.run(debug=True)


