import json
from gluon import current
from datetime import datetime, timedelta, date
import logging
from decimal import Decimal
import datetime
from io import StringIO
from gluon.contrib.pymysql.err import IntegrityError

def registrar_log(entidade, registro_id, acao, estado_anterior=None):
    """Registra uma ação no log geral do sistema.

    Args:
        entidade (str): Nome da entidade afetada (ex: 'estoque', 'auth_user').
        registro_id (int): ID do registro afetado na entidade.
        acao (str): Tipo de ação ('exclusao' ou 'alteracao').
        estado_anterior (dict, opcional): Estado anterior do registro, caso seja uma alteração.
    """
    db.log_sistema.insert(
        user_id=auth.user_id,
        entidade=entidade,
        acao=acao,
        registro_id=registro_id,
        observacao=estado_anterior,
        timestamp=request.now
    )
    db.commit()

@auth.requires_login()
def index():
    nome_filtro = request.vars.nome or ''
    tipo_filtro = request.vars.tipo or ''
    dia_filtro = request.vars.dia_semana or ''
    pagina = int(request.vars.pagina or 1)
    registros_por_pagina = 10
    inicio = (pagina - 1) * registros_por_pagina
    fim = inicio + registros_por_pagina

    # Query
    query = db.cardapio.id > 0  # Sempre retorna True para construir a base da query
    if nome_filtro:
        query &= db.cardapio.nome.contains(nome_filtro)
    if tipo_filtro:
        query &= (db.cardapio.tipo == tipo_filtro)
    if dia_filtro:
        query &= (db.cardapio.dias_semana.contains(dia_filtro))

    # Conta total de registros filtrados
    total_cardapio = db(query).count()

    # Consulta com paginação
    cardapio = db(query).select(limitby=(inicio, fim))

    # Cache para valores de tipos distintos
    tipos = cache.ram('tipos_cardapio', lambda: db(db.cardapio).select(db.cardapio.tipo, distinct=True), time_expire=300)

    # Cálculo de total de páginas
    total_paginas = (total_cardapio + registros_por_pagina - 1) // registros_por_pagina

    return dict(
        cardapio=cardapio,
        tipos=tipos,
        nome_filtro=nome_filtro,
        tipo_filtro=tipo_filtro,
        dia_filtro=dia_filtro,
        pagina=pagina,
        total_cardapio=total_cardapio,
        registros_por_pagina=registros_por_pagina,
        total_paginas=total_paginas
    )


@auth.requires_login()
def visualizar_cardapio():
    cardapio_id = request.args(0) or redirect(URL('index'))

    prato = db.cardapio(cardapio_id) or redirect(URL('index'))

    try:
        ingredientes = prato.ingredientes if isinstance(prato.ingredientes, list) else json.loads(prato.ingredientes or '[]')
        tipos_usuario = prato.tipos_usuario if isinstance(prato.tipos_usuario, list) else json.loads(prato.tipos_usuario or '[]')
        dias_semana = prato.dias_semana if isinstance(prato.dias_semana, list) else json.loads(prato.dias_semana or '[]')
    except (TypeError, json.JSONDecodeError) as e:
        response.flash = f"Erro ao processar JSON: {str(e)}"
        ingredientes, tipos_usuario, dias_semana = [], [], []

    return dict(prato=prato, ingredientes=ingredientes, tipos_usuario=tipos_usuario, dias_semana=dias_semana)

@auth.requires_login()
def cadastrar_cardapio():
    app_name = request.application
    ingredientes_disponiveis = db(db.estoque).select(orderby=db.estoque.nome)
    tipos_refeicoes = db(db.horario_refeicoes).select(db.horario_refeicoes.refeicao, distinct=True)
    
    # Buscar tipos de usuário do banco de dados
    tipos_usuario = db(db.user_type).select(orderby=db.user_type.name)

    return dict(
        ingredientes_disponiveis=ingredientes_disponiveis, 
        tipos_refeicoes=tipos_refeicoes, 
        tipos_usuario=tipos_usuario,
        app_name=app_name
    )

@auth.requires_login()
def editar_cardapio():
    cardapio_id = request.args(0)
    app_name = request.application
    tipos_refeicoes = db(db.horario_refeicoes).select(db.horario_refeicoes.refeicao, distinct=True)

    cardapio = db.cardapio(cardapio_id)

    if not cardapio:
        session.flash = "Item do cardápio não encontrado."
        redirect(URL('index'))

    # Captura o estado anterior do cardápio antes da edição
    estado_anterior = {
        'nome': cardapio.nome,
        'tipo': cardapio.tipo,
        'preco': cardapio.preco,
    }

    # Registrar log
    registrar_log(entidade='cardapio', registro_id=cardapio_id, acao='edição', estado_anterior=estado_anterior)

    # Buscar tipos de usuário do banco de dados
    tipos_usuario = db(db.user_type).select(orderby=db.user_type.name)
    
    ingredientes_disponiveis = db(db.estoque).select(orderby=db.estoque.nome)

    return dict(
        ingredientes_disponiveis=ingredientes_disponiveis, 
        app_name=app_name, 
        cardapio=cardapio, 
        tipos_usuario=tipos_usuario,
        tipos_refeicoes=tipos_refeicoes
    )

@auth.requires_login()
def api_criar_cardapio():
    if request.env.request_method == 'POST':
        try:
            dados = request.post_vars

            nome = dados.get('nome')
            descricao = dados.get('descricao')
            preco = dados.get('preco')
            tipo = dados.get('tipo')
            ingredientes = json.loads(dados.get('ingredientes', '[]'))
            tipos_usuario = json.loads(dados.get('tipos_usuario', '[]'))
            dias_semana = json.loads(dados.get('dias_semana', '[]'))
            foto_do_prato_base64 = dados.get('foto_do_prato')

            # Verificar se o nome já existe
            if db(db.cardapio.nome == nome).count() > 0:
                return response.json({'status': 'error', 'message': 'Nome de cardápio já cadastrado.'})

            # Inserir o novo cardápio
            cardapio_id = db.cardapio.insert(
                nome=nome,
                descricao=descricao,
                tipo=tipo,
                preco=preco,
                ingredientes=ingredientes,
                tipos_usuario=tipos_usuario,
                dias_semana=dias_semana,
                foto_do_prato=foto_do_prato_base64
            )
            db.commit()

            return response.json({'status': 'success', 'message': 'Cardápio cadastrado com sucesso!', 'cardapio_id': cardapio_id})
        except Exception as e:
            return response.json({'status': 'error', 'message': str(e)})
    else:
        return response.json({'status': 'error', 'message': 'Método inválido. Use POST.'})

@auth.requires_login()
def api_editar_cardapio():
    """
    API para edição de itens do cardápio.
    Recebe dados em formato JSON e retorna resposta em JSON.
    """
    import json
    import logging
    
    # Configurar logger
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger('cardapio_edit')
    
    # Definir tipo de conteúdo da resposta
    response.headers['Content-Type'] = 'application/json'
    
    if request.env.request_method == 'POST':
        try:
            # Obter os dados JSON do corpo da requisição
            data = request.body.read().decode('utf-8')
            logger.info(f"Dados recebidos para edição de cardápio")
            
            # Analisar dados JSON
            dados = json.loads(data)
            
            # Extrair valores principais
            cardapio_id = dados.get('id')
            nome = dados.get('nome')
            descricao = dados.get('descricao')
            tipo = dados.get('tipo')
            preco = dados.get('preco')
            
            # Validar ID
            if not cardapio_id:
                logger.error("ID do cardápio não fornecido")
                return json.dumps({'status': 'error', 'message': 'ID do cardápio é obrigatório'})
            
            # Analisar estruturas JSON complexas
            try:
                ingredientes_str = dados.get('ingredientes', '[]')
                ingredientes = json.loads(ingredientes_str)
            except Exception as e:
                logger.error(f"Erro ao analisar ingredientes: {e}")
                ingredientes = []
                
            try:
                tipos_usuario_str = dados.get('tipos_usuario', '[]')
                tipos_usuario = json.loads(tipos_usuario_str)
                logger.info(f"Tipos de usuário analisados: {tipos_usuario}")
            except Exception as e:
                logger.error(f"Erro ao analisar tipos_usuario: {e}")
                tipos_usuario = []
                
            try:
                dias_semana_str = dados.get('dias_semana', '[]')
                dias_semana = json.loads(dias_semana_str)
            except Exception as e:
                logger.error(f"Erro ao analisar dias_semana: {e}")
                dias_semana = []
                
            # Obter dados da imagem
            foto_do_prato_base64 = dados.get('foto_do_prato')
                
            # Buscar o item do cardápio existente
            cardapio_existente = db(db.cardapio.id == cardapio_id).select().first()
            if not cardapio_existente:
                logger.error(f"Item do cardápio com ID {cardapio_id} não encontrado")
                return json.dumps({'status': 'error', 'message': 'Item do cardápio não encontrado'})

            # Atualizar o registro no banco de dados
            try:
                # Manter foto atual se não for fornecida nova
                if not foto_do_prato_base64:
                    nova_foto = cardapio_existente.foto_do_prato
                else:
                    nova_foto = foto_do_prato_base64
                
                # Capturar estado anterior para log
                estado_anterior = {
                    'nome': cardapio_existente.nome,
                    'tipo': cardapio_existente.tipo,
                    'preco': cardapio_existente.preco,
                    'tipos_usuario': cardapio_existente.tipos_usuario
                }
                
                # Atualizar o registro
                cardapio_existente.update_record(
                    nome=nome,
                    descricao=descricao,
                    tipo=tipo,
                    preco=preco,
                    ingredientes=ingredientes,
                    tipos_usuario=tipos_usuario,
                    dias_semana=dias_semana,
                    foto_do_prato=nova_foto
                )
                db.commit()
                
                # Registrar log
                try:
                    registrar_log(
                        entidade='cardapio', 
                        registro_id=cardapio_id, 
                        acao='edição', 
                        estado_anterior=estado_anterior
                    )
                except Exception as log_error:
                    logger.error(f"Erro ao registrar log: {log_error}")
                
                logger.info(f"Item do cardápio ID {cardapio_id} atualizado com sucesso")
                return json.dumps({
                    'status': 'success', 
                    'message': 'Cardápio atualizado com sucesso!', 
                    'cardapio_id': cardapio_id
                })
            except Exception as update_error:
                db.rollback()
                logger.error(f"Erro ao atualizar cardápio: {update_error}")
                return json.dumps({'status': 'error', 'message': f'Erro ao atualizar: {str(update_error)}'})
                
        except Exception as e:
            logger.error(f"Erro geral na API: {e}")
            return json.dumps({'status': 'error', 'message': f'Erro no processamento: {str(e)}'})
    else:
        # Método HTTP não permitido
        logger.warning(f"Tentativa de acesso com método {request.env.request_method}")
        return json.dumps({'status': 'error', 'message': 'Método não permitido. Use POST.'})

@auth.requires_login()
def visualizar_cardapio_api():
    cardapio_id = request.args(0) or redirect(URL('index'))

    prato = db.cardapio(cardapio_id) or redirect(URL('index'))

    try:
        ingredientes = json.loads(prato.ingredientes) if isinstance(prato.ingredientes, str) else (prato.ingredientes or [])
        tipos_usuario = json.loads(prato.tipos_usuario) if isinstance(prato.tipos_usuario, str) else (prato.tipos_usuario or [])
        dias_semana = json.loads(prato.dias_semana) if isinstance(prato.dias_semana, str) else (prato.dias_semana or [])
    except (TypeError, json.JSONDecodeError) as e:
        response.status = 400
        return response.json(dict(status='error', message=f"Erro ao processar JSON: {str(e)}"))

    return response.json(dict(
        status='success',
        prato=dict(
            nome=prato.nome,
            preco=prato.preco,
            descricao=prato.descricao,
            tipo=prato.tipo,
            ingredientes=ingredientes,
            tipos_usuario=tipos_usuario,
            dias_semana=dias_semana,
            foto_do_prato=prato.foto_do_prato
        )
    ))

@auth.requires_login()
@auth.requires_login()
def excluir_cardapio():
    try:
        cardapio_id = request.args(0, cast=int)

        cardapio = db.cardapio(cardapio_id)

        # Captura o estado anterior do colaborador antes da edição
        estado_anterior = {
            'nome': cardapio.nome,
            'tipo': cardapio.tipo,
            'preco': cardapio.preco,
        }

        registrar_log(entidade='cardapio', registro_id=cardapio_id, acao='exclusão', estado_anterior=estado_anterior)


        if cardapio:
            db(db.cardapio.id == cardapio_id).delete()
            db.commit()
            response.flash = "Cardápio excluído com sucesso!"
        else:
            response.flash = "Cardápio não encontrado."
    except Exception as e:
        response.flash = f"Erro ao excluir o cardápio: {e}"

    redirect(URL('index'))


@auth.requires_login()
def listar_cardapio_mobile():
    """
    Renderiza a tela de listagem de cardápio para dispositivos móveis.
    """
    return dict()



def registrar_log(entidade, registro_id, acao, estado_anterior=None):
    """Registra uma ação no log geral do sistema.

    Args:
        entidade (str): Nome da entidade afetada (ex: 'estoque', 'auth_user').
        registro_id (int): ID do registro afetado na entidade.
        acao (str): Tipo de ação ('exclusao' ou 'alteracao').
        estado_anterior (dict, opcional): Estado anterior do registro, caso seja uma alteração.
    """
    db.log_sistema.insert(
        user_id=auth.user_id,
        entidade=entidade,
        acao=acao,
        registro_id=registro_id,
        observacao=estado_anterior,
        timestamp=request.now
    )
    db.commit()






@auth.requires_login()
def admin_cardapio():
    nome_filtro = request.vars.nome or ''
    tipo_filtro = request.vars.tipo or ''
    dia_filtro = request.vars.dia_semana or ''
    pagina = int(request.vars.pagina or 1)
    registros_por_pagina = 10
    inicio = (pagina - 1) * registros_por_pagina
    fim = inicio + registros_por_pagina

    # Query
    query = db.cardapio.id > 0  # Sempre retorna True para construir a base da query
    if nome_filtro:
        query &= db.cardapio.nome.contains(nome_filtro)
    if tipo_filtro:
        query &= (db.cardapio.tipo == tipo_filtro)
    if dia_filtro:
        query &= (db.cardapio.dias_semana.contains(dia_filtro))

    # Conta total de registros filtrados
    total_cardapio = db(query).count()

    # Consulta com paginação
    cardapio = db(query).select(limitby=(inicio, fim))

    # Cache para valores de tipos distintos
    tipos = cache.ram('tipos_cardapio', lambda: db(db.cardapio).select(db.cardapio.tipo, distinct=True), time_expire=300)

    # Cálculo de total de páginas
    total_paginas = (total_cardapio + registros_por_pagina - 1) // registros_por_pagina

    return dict(
        cardapio=cardapio,
        tipos=tipos,
        nome_filtro=nome_filtro,
        tipo_filtro=tipo_filtro,
        dia_filtro=dia_filtro,
        pagina=pagina,
        total_cardapio=total_cardapio,
        registros_por_pagina=registros_por_pagina,
        total_paginas=total_paginas
    )

@auth.requires_login()
def pesquisar_usuarios():
    """
    Endpoint para pesquisar usuários por nome.
    Aceita parâmetros via GET para facilitar o cache e recarregamento.
    """
    termo = request.vars.termo or ''
    limite = int(request.vars.limite or 20)
    
    if not termo or len(termo.strip()) < 3:
        return response.json({'status': 'error', 'message': 'Digite pelo menos 3 caracteres para pesquisar'})
    
    # Recupera os IDs dos tipos permitidos (mesma lógica que já usava)
    tipos_permitidos = ['Paciente', 'Paciente Convenio', 'Colaborador']
    tipos_ids = db(db.user_type.name.belongs(tipos_permitidos)).select(db.user_type.id)
    tipos_ids = [tipo.id for tipo in tipos_ids]
    
    # Consulta com filtro de nome e tipo de usuário
    query = db.auth_user.user_type.belongs(tipos_ids)
    termo = termo.strip().lower()
    
    # Filtro para buscar por nome ou sobrenome que contém o termo
    query &= ((db.auth_user.first_name.lower().contains(termo)) | 
              (db.auth_user.last_name.lower().contains(termo)))
    
    # Execute a consulta com limite para melhor performance
    usuarios = db(query).select(
        db.auth_user.id,
        db.auth_user.first_name,
        db.auth_user.last_name,
        db.auth_user.user_type,
        limitby=(0, limite),
        orderby=db.auth_user.first_name
    )
    
    # Formata o resultado para retorno
    resultado = []
    for u in usuarios:
        tipo = db.user_type(u.user_type)
        resultado.append({
            'id': u.id,
            'first_name': u.first_name,
            'last_name': u.last_name,
            'user_type': tipo.name if tipo else "Desconhecido",
            'nome_completo': f"{u.first_name} {u.last_name}"
        })
    
    return response.json({
        'status': 'success',
        'usuarios': resultado,
        'total': len(resultado)
    })


@auth.requires_login()
def api_listar_pratos_para_usuario():
        return response.json({'status': 'error', 'message': str(e)})




def api_listar_usuarios_para_excecao():
    try:
        # Recupera os IDs dos tipos permitidos
        tipos_permitidos = ['Paciente', 'Paciente Convenio', 'Colaborador']
        tipos_ids = db(db.user_type.name.belongs(tipos_permitidos)).select(db.user_type.id)
        tipos_ids = [tipo.id for tipo in tipos_ids]

        # Busca os usuários com esses tipos
        usuarios = db(db.auth_user.user_type.belongs(tipos_ids)).select(
            db.auth_user.id,
            db.auth_user.first_name,
            db.auth_user.last_name,
            db.auth_user.user_type
        )

        resultado = []
        for u in usuarios:
            # Aqui acessamos o nome do tipo referenciado corretamente
            tipo = db.user_type(u.user_type)
            resultado.append({
                'id': u.id,
                'first_name': u.first_name,
                'last_name': u.last_name,
                'user_type': tipo.name if tipo else "Desconhecido"
            })

        return response.json({'status': 'success', 'usuarios': resultado})

    except Exception as e:
        return response.json({'status': 'error', 'message': str(e)})


def api_listar_pratos_excessao():
    try:
        pratos = db(db.cardapio).select()

        pratos_formatados = []
        for prato in pratos:

            pratos_formatados.append({
                'id': prato.id,
                'nome': prato.nome,
                'descricao': prato.descricao,
                'preco': float(prato.preco),
            })

        return response.json({'status': 'success', 'pratos': pratos_formatados})

    except Exception as e:
        return response.json({'status': 'error', 'message': str(e)})



def api_registrar_solicitacao_excecao():
    if request.env.request_method == 'POST':
        try:
            # Compatível com JSON ou POST
            if request.env.content_type == 'application/json':
                dados = request.body.read()
                dados = json.loads(dados) if dados else {}
            else:
                dados = request.post_vars

            solicitante_id = int(dados.get('solicitante_id'))
            prato_id = int(dados.get('pratoid'))
            quantidade = int(dados.get('quantidade'))
            preco = Decimal(dados.get('preco'))
            descricao = dados.get('descricao', '')
            status = 'Pendente'

            # Valida prato
            prato = db.cardapio(prato_id)
            if not prato:
                raise ValueError("Prato não encontrado.")

            # Inserção da solicitação
            solicitacao_id = db.solicitacao_refeicao.insert(
                solicitante_id=solicitante_id,
                prato_id=prato_id,
                preco=preco,
                quantidade_solicitada=quantidade,
                descricao=descricao,
                status=status,
                is_acompanhante=0
            )

            # Atualiza saldo do usuário
            saldo = db(db.user_balance.user_id == solicitante_id).select().first()
            if saldo:
                saldo.update_record(saldo_devedor=saldo.saldo_devedor + preco)
            else:
                db.user_balance.insert(user_id=solicitante_id, saldo_devedor=preco)

            db.commit()
            return response.json({'status': 'success', 'solicitacao_id': solicitacao_id})

        except Exception as e:
            db.rollback()
            return response.json({'status': 'error', 'message': str(e)})
    else:
        return response.json({'status': 'error', 'message': 'Método inválido. Use POST.'})



