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
if not firebase_admin._apps:
    if os.getenv('VERCEL'):
        cred = credentials.Certificate(json.loads(os.getenv('FIREBASE_CREDENTIALS')))
    else:
        cred = credentials.Certificate("firebase.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

# 2. Configuração do Flask
app = Flask(__name__)
CORS(app, origins="*") # Permite que qualquer origem acesse a API.
# versão openapi 
app.config['SWAGGER']={
    'openapi': '3.0.3'

}
#chamar o openapi para o código 
swagger=Swagger(app, template_file='openapi.yaml') #template_file é o arquivo onde está a documentação da api, ou seja, o openapi.yaml

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
    try:
        dados = request.get_json()
        
        if not dados or "cpf" not in dados:
            return jsonify({"erro": "CPF não informado"}), 400
            
        # Limpa o CPF (remove pontos, traços e espaços)
        cpf_recebido = ''.join(filter(str.isdigit, str(dados.get("cpf"))))

        # Busca limitada a 1 resultado para performance
        resultado_busca = db.collection('alunos').where('cpf', '==', cpf_recebido).limit(1).get()

        aluno_doc = None
        for item in resultado_busca:
            aluno_doc = item.to_dict()

        if not aluno_doc:
            return jsonify({
                "status": "BLOQUEADO", 
                "mensagem": "CPF não cadastrado"
            }), 404

        # VERIFICAÇÃO CRÍTICA: O aluno está ativo?
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
            }), 403 # 403 Forbidden é mais apropriado para bloqueios

    except Exception as e:
        print(f"ERRO DE SISTEMA: {e}")
        return jsonify({
            "status": "ERRO_SISTEMA",
            "mensagem": "Falha na comunicação com o banco de dados."
        }), 503

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
        cpf_entrada = str(dados.get("cpf")).strip()
        
        # 1. VALIDAÇÃO DE LETRAS
        # Se houver qualquer letra no que o usuário digitou, rejeita na hora
        if any(char.isalpha() for char in cpf_entrada):
            return jsonify({
                "erro": "CPF inválido. O campo não pode conter letras, apenas números, pontos e traços."
            }), 400

        # 2. LIMPEZA (Saneamento)
        # Agora que sabemos que não há letras, removemos '.' e '-' para ter o número puro
        cpf_limpo = ''.join(filter(str.isdigit, cpf_entrada))

        # 3. VALIDAÇÃO DE TAMANHO
        if len(cpf_limpo) != 11:
            return jsonify({
                "erro": "CPF incompleto. Certifique-se de que digitou os 11 números."
            }), 400

        # 4. VERIFICAÇÃO DE DUPLICIDADE
        conferir_cpf = db.collection('alunos').where('cpf', '==', cpf_limpo).get()
        if len(conferir_cpf) > 0:
            return jsonify({"erro": "Este CPF já está cadastrado."}), 409 

        # 5. GERENCIAMENTO DE ID E INSERÇÃO
        contador_ref = db.collection('contador').document('controle_de_id')
        contador_doc = contador_ref.get()
        
        ultimo_id = 0
        if contador_doc.exists:
            ultimo_id = contador_doc.to_dict().get('ultimo_id', 0)
        
        novo_id = ultimo_id + 1
        contador_ref.set({'ultimo_id': novo_id}) 

        db.collection('alunos').add({
            "id": int(novo_id),
            "nome": str(dados.get("nome")).strip(),
            "cpf": cpf_limpo, # Salva o número puro (ex: 99999999999)
            "status": str(dados.get("status", "ATIVO")).upper() 
        })

        return jsonify({"mensagem": "Aluno salvo!", "id": novo_id}), 201

    except Exception as e:
        return jsonify({"erro": f"Erro interno: {str(e)}"}), 500

@app.route("/alunos/<int:id>", methods=['PUT'])
@token_obrigatorio
def atualizar_aluno_total(id):
    dados = request.get_json()
    
    if not dados or not all(k in dados for k in ("nome", "cpf", "status")):
        return jsonify({"erro": "Dados incompletos para atualização."}), 400

    try:
        # 1. Garante a limpeza do CPF também na edição
        cpf_limpo = ''.join(filter(str.isdigit, str(dados.get("cpf"))))
        
        # 2. Busca o documento que contém o campo 'id' igual ao ID da URL
        # Importante: o campo no Firestore deve ser um Number
        docs = db.collection('alunos').where('id', '==', int(id)).get()

        if not docs:
            return jsonify({"erro": f"Aluno com ID {id} não encontrado"}), 404
        
        # Pega a referência do primeiro documento encontrado
        doc_ref = docs[0].reference 

        # 3. Atualiza os dados
        doc_ref.update({
            "nome": str(dados.get("nome")).strip(),
            "cpf": cpf_limpo,
            "status": str(dados.get("status")).upper()
        })
        
        return jsonify({"mensagem": "Aluno atualizado com sucesso!"}), 200

    except Exception as e:
        print(f"Erro no PUT: {e}") # Log para você ver no terminal/Vercel
        return jsonify({"erro": f"Erro interno: {str(e)}"}), 500

# ========================================================================
#   ALUNOS: ATUALIZAÇÃO PARCIAL (PATCH)
# ========================================================================

@app.route("/alunos/<int:id>", methods=['PATCH'])
@token_obrigatorio
def atualizar_aluno_parcial(id):
    dados = request.get_json()
    if not dados:
        return jsonify({"erro": "Nenhum dado enviado."}), 400

    try:
        docs = db.collection('alunos').where('id', '==', int(id)).limit(1).get()

        if not docs:
            return jsonify({"erro": "Aluno não encontrado"}), 404
        
        doc_ref = docs[0].reference
        update_aluno = {}

        # Só adiciona ao dicionário o que foi enviado no JSON
        if 'nome' in dados:
            update_aluno['nome'] = str(dados['nome']).strip()
        if 'cpf' in dados:
            update_aluno['cpf'] = str(dados['cpf']).strip()
        if 'status' in dados:
            update_aluno['status'] = str(dados['status']).upper()
        
        if not update_aluno:
            return jsonify({"erro": "Campos inválidos para atualização."}), 400

        doc_ref.update(update_aluno)
        return jsonify({"mensagem": "Sucesso na atualização parcial (PATCH)!"}), 200
        
    except Exception as e:
        return jsonify({"erro": f"Erro ao atualizar: {str(e)}"}), 500
        
       

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
#   ZONA DE ERROS: TRATAMENTO DE EXCEÇÕES PARA EVITAR TRAVAMENTO INFINITO E FORNECER RESPOSTAS ÚTEIS
# ========================================================================


@app.errorhandler(500)
def erro_interno(e):
    return jsonify({
        "status": "OFFLINE",
        "erro": "Erro interno no servidor ou falha de conexão com o banco de dados.",
        "mensagem": "Verifique a conexão de rede ou o status do serviço Firebase."
    }), 500

@app.errorhandler(Exception)
def lidar_com_excecao_generica(e):
    # Captura qualquer erro não esperado e evita travamento infinito
    return jsonify({
        "status": "ERRO",
        "erro": str(e),
        "mensagem": "A requisição falhou. Tente novamente em instantes."
    }), 500

if __name__ == '__main__':
    app.run(debug=True)


