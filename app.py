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

load_dotenv() # Carrega as variáveis de ambiente do arquivo .env para o ambiente de execução do phyton. 

# 1. Configuração do Firebase
if os.getenv('VERCEL'):
    #onlien na vercel 
    cred=credentials.Certificate(json.loads(os.getenv('FIREBASE_CREDENTIALS'))) #loads puxa  arquivo, ja o load puxa uma string 
else:
    #localmente
    cred=credentials.Certificate("firebase.json")


firebase_admin.initialize_app(cred)
db = firestore.client()

# 2. Configuração do Flask
app = Flask(__name__)
CORS(app)
# versão openapi 
app.config['SWAGGER']={
    'openapi': '3.0.3'

}
#chamar o openapi para o código 
swagger=Swagger(app, template_file='openapi.yaml') #template_file é o arquivo onde está a documentação da api, ou seja, o openapi.yaml

app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
CORS(app, origins="*")

adm_usuario = os.getenv('ADM_USUARIO')
adm_senha = os.getenv('ADM_SENHA')
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
    
    # Verifica as credenciais baseadas no seu .env
    if dados.get("usuario") == adm_usuario and dados.get("senha") == adm_senha:
        payload = {
            "usuario": adm_usuario,
            "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=24) # Token vale 1 dia
        }
        token = jwt.encode(payload, app.config['SECRET_KEY'], algorithm="HS256")
        return jsonify({"token": token}), 200
    
    return jsonify({"erro": "Credenciais incorretas"}), 401



# ========================================================================
#   APLICAÇÃO 1: CATRACA tablet da portaria
# ========================================================================

@app.route("/catraca", methods=['POST'])
def consultar_acesso():
    dados = request.get_json()
    cpf_recebido = dados.get("cpf")

    resultado_busca = db.collection('alunos').where('cpf', '==', cpf_recebido).get()

    aluno_encontrado = None
    for item in resultado_busca:
        aluno_encontrado = item.to_dict()

    if not aluno_encontrado:
        return jsonify({"status": "BLOQUEADO", "mensagem": "CPF não cadastrado"}), 404

    return jsonify({
        "nome": aluno_encontrado.get("nome"),
        "status": aluno_encontrado.get("status")
    }), 200

# ========================================================================
#   APLICAÇÃO 3: FRONTEND
# ========================================================================

@app.route("/alunos", methods=['POST'])
@token_obrigatorio
def cadastrar_aluno():
    dados = request.get_json()

    if not dados or 'cpf' not in dados or 'nome' not in dados:
        return jsonify({"erro": "Dados incompletos."}), 400
    
    try:
        # Lógica do contador automático
        contador_ref = db.collection('contador').document('controle_de_id')
        contador_doc = contador_ref.get()
        
        # Se o contador não existir, começa do 0
        ultimo_id = 0
        if contador_doc.exists:
            ultimo_id = contador_doc.to_dict().get('ultimo_id', 0)
        
        novo_id = ultimo_id + 1
        contador_ref.set({'ultimo_id': novo_id}) # Atualiza o contador

        db.collection('alunos').add({
            "id": novo_id,
            "nome": dados.get("nome"),
            "cpf": dados.get("cpf"),
            "status": dados.get("status", "ATIVO") # Padrão é ATIVO se não enviar
        })
        return jsonify({"mensagem": "Aluno salvo!", "id": novo_id}), 201
    except:
        return jsonify({"erro": "Erro ao salvar no banco."}), 500

@app.route("/alunos", methods=['GET'])
@token_obrigatorio
def listar_todos_alunos():
    lista = []
    todos_os_docs = db.collection('alunos').get()
    for doc in todos_os_docs:
        lista.append(doc.to_dict())
    return jsonify(lista), 200

@app.route("/alunos/<int:id>", methods=['PUT'])
@token_obrigatorio
def atualizar_aluno_total(id):
    dados = request.get_json()
    
    # No PUT, geralmente validamos se todos os campos obrigatórios foram enviados
    if not dados or not all(k in dados for k in ("nome", "cpf", "status")):
        return jsonify({"erro": "Dados incompletos para atualização total (PUT)."}), 400

    try:
        # Busca o documento pelo campo 'id' numérico
        docs = db.collection('alunos').where('id', '==', id).limit(1).get()

        if len(docs) == 0:
            return jsonify({"erro": "Aluno não encontrado"}), 404
        
        # Pega a referência do primeiro documento encontrado
        doc_ref = docs[0].reference 

        # No PUT, atualizamos todos os campos obrigatórios
        doc_ref.update({
            "nome": dados.get("nome"),
            "cpf": dados.get("cpf"),
            "status": dados.get("status")
        })
        
        return jsonify({"mensagem": "Aluno atualizado com sucesso (PUT)!"}), 200

    except :
        return jsonify({"erro": "Erro interno ao atualizar o aluno."}), 500

@app.route("/alunos/<int:id>", methods=['PATCH'])
@token_obrigatorio
def atualizar_aluno(id):
    dados = request.get_json()
    if not dados or ('nome' not in dados and 'cpf' not in dados and 'status' not in dados):
        return jsonify({"erro": "Nenhum dado para atualizar."}), 400

    try:
        docs = db.collection('alunos').where('id', '==', id).limit(1).get()

        if not docs:
            return jsonify({"erro": "Aluno não encontrado"}), 404
        
        doc_ref=db.collection('alunos').document(docs[0].id)
        update_aluno = {}
        if 'nome' in dados:
            update_aluno['nome'] = dados['nome']
        if 'cpf' in dados:
            update_aluno['cpf'] = dados['cpf']
        if 'status' in dados:
            update_aluno['status'] = dados['status']
        
        doc_ref.update(update_aluno)
        return jsonify({"mensagem": "Sucesso!"}), 200
    except:
        return jsonify({"erro": "Erro ao atualizar."}), 500
        
        
       

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

if __name__ == '__main__':
    app.run(debug=True)
      


