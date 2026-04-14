
import jwt
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import request, jsonify, current_app



# ==========================
# FUNÇÃO PARA GERAR TOKEN JWT
# ==========================
def gerar_token(usuario):
    """
    Gera um token JWT com tempo de expiração.

    Parâmetro:
    - usuario: nome do usuário autenticado

    Retorno:
    - token JWT assinado com a SECRET_KEY da aplicação
    """
    payload = {
        "usuario": usuario,# Você pode incluir outras informações no payload, como ID do usuário, permissões, etc.
        "perfil": "adm",# Você pode adicionar mais informações ao payload, como perfil de acesso
        "exp": datetime.now(timezone.utc) + timedelta(hours=24) # O token expira em 24 horas
    }

#exp siginifica expiration, ou seja, a data e hora de expiração do token. O JWT incluirá essa informação e, ao tentar usar o token após esse horário, ele será considerado inválido.

    # Gera o token JWT usando a chave secreta da aplicação
    token = jwt.encode(
        payload,
        current_app.config["SECRET_KEY"],
        algorithm="HS256" # O algoritmo de assinatura usado para criar o token. HS256 é um algoritmo de hash simétrico que usa a chave secreta para assinar o token. Certifique-se de usar uma chave secreta forte e mantê-la segura.
    )

    return token


# o decorator no python é uma função que recebe outra função como argumento e retorna uma nova função que geralmente adiciona algum tipo de funcionalidade ou comportamento à função original. No caso do token_obrigatorio, ele é usado para proteger rotas específicas, exigindo que o cliente forneça um token JWT válido para acessar essas rotas.
# ==========================
# DECORATOR PARA PROTEGER ROTAS
# ==========================


def token_obrigatorio(func):
    """
    Decorator que exige um token JWT válido para acessar a rota.

    Uso:
    @app.route('/rota-privada')
    @token_obrigatorio
    def minha_rota():
        ...
    """
    @wraps(func)
    def verificar_token(*args, **kwargs):
        auth_header = request.headers.get("Authorization")

        # Verifica se o cabeçalho foi enviado
        if not auth_header:
            return jsonify({"erro": "Token ausente. Faça login."}), 401

        partes = auth_header.split()

        # Verifica se o formato está correto: Bearer SEU_TOKEN
        if len(partes) != 2 or partes[0] != "Bearer":
            return jsonify({"erro": "Cabeçalho Authorization inválido."}), 401

        token = partes[1]

        try:
            # Tenta decodificar o token usando a chave secreta
            dados_token = jwt.decode(
                token,
                current_app.config["SECRET_KEY"],
                algorithms=["HS256"]
            )

            # Se quiser, depois você pode usar esses dados dentro da rota
            request.usuario_logado = dados_token

        except jwt.ExpiredSignatureError:
            return jsonify({"erro": "Token expirado. Faça login novamente."}), 401

        except jwt.InvalidTokenError:
            return jsonify({"erro": "Token inválido."}), 401

        return func(*args, **kwargs)

    return verificar_token