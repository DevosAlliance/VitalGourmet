import json
from gluon import current
from datetime import datetime, timedelta, date
import logging
from decimal import Decimal
import datetime
from io import StringIO
from gluon.contrib.pymysql.err import IntegrityError


@auth.requires_login()
def index():
    nome_filtro = request.vars.nome or ''
    ordem = request.vars.ordem or 'asc'
    pagina = int(request.vars.pagina or 1)
    registros_por_pagina = 10
    inicio = (pagina - 1) * registros_por_pagina
    fim = inicio + registros_por_pagina

    # Filtragem e Ordenação
    query = db.estoque.nome.contains(nome_filtro) if nome_filtro else db.estoque.id > 0
    orderby = db.estoque.gramatura if ordem == 'asc' else ~db.estoque.gramatura

    # Obtenção de Itens com Paginação
    total_items = db(query).count()
    estoque_items = db(query).select(orderby=orderby, limitby=(inicio, fim))

    return dict(
        estoque_items=estoque_items,
        nome_filtro=nome_filtro,
        ordem=ordem,
        pagina=pagina,
        total_items=total_items,
        registros_por_pagina=registros_por_pagina
    )

@auth.requires_login()
def cadastrar_estoque():
    if request.env.request_method == 'POST':
        nome = request.post_vars.get('nome')
        gramatura = request.post_vars.get('gramatura')

        existe = db(db.estoque.nome == nome).select().first()
        if existe:
            session.flash = 'Nome já cadastrado'
            redirect(URL('index'))

        db.estoque.insert(nome=nome, gramatura=gramatura)
        session.flash = 'Item cadastrado com sucesso!'
        redirect(URL('index'))

    return dict()

@auth.requires_login()
def verificar_nome():
    nome = request.vars.get('nome')
    existe = db(db.estoque.nome == nome).count() > 0
    return response.json({'exists': existe})




@auth.requires_login()
def editar_estoque():
    try:
        # Recebe os dados do formulário enviado via AJAX
        estoque_id = request.post_vars['id']
        nome = request.post_vars['nome']
        gramatura = request.post_vars['gramatura']
        
        # Validação adicional
        if not nome or not gramatura:
            return response.json({'status': 'failed', 'message': 'Nome e gramatura são obrigatórios'})
            
        # Busca o item no banco de dados
        estoque_item = db.estoque(estoque_id)
        
        if not estoque_item:
            return response.json({'status': 'failed', 'message': 'Item não encontrado'})
            
        # Captura o estado anterior do item antes da edição
        estado_anterior = {
            'nome': estoque_item.nome,
            'gramatura': estoque_item.gramatura,
        }
        
        # Atualiza os dados
        estoque_item.update_record(nome=nome, gramatura=gramatura)
        db.commit()
        
        # Registra o log após o commit bem-sucedido
        registrar_log(entidade='Estoque', registro_id=estoque_id, acao='edição', estado_anterior=estado_anterior)
        
        return response.json({'status': 'success', 'message': 'Item atualizado com sucesso'})
    except Exception as e:
        # Rollback em caso de erro
        db.rollback()
        import traceback
        erro_detalhado = traceback.format_exc()
        return response.json({'status': 'failed', 'message': str(e), 'details': erro_detalhado})
    
    
@auth.requires_login()
def deletar_estoque():
    """
    Função para excluir um item do estoque com log de exclusão.
    Redireciona para a visualização do estoque após a exclusão.
    """
    # Obtém o ID do item a ser excluído, passado via URL
    estoque_id = request.args(0)
    if not estoque_id:
        response.flash = 'ID do item não fornecido!'
        redirect(URL('visualizar_estoque'))
    
    # Busca o item no banco de dados
    item = db.estoque(estoque_id)
    if not item:
        response.flash = 'Item não encontrado!'
        redirect(URL('visualizar_estoque'))
    
    # Captura o estado anterior do item para registro no log
    estado_anterior = {
        'nome': item.nome,
        'gramatura': item.gramatura,
        # Adicione mais campos conforme necessário
    }

    try:
        # Registra o log de exclusão
        registrar_log(
            entidade='estoque',
            registro_id=estoque_id,
            acao='Exclusão',
            estado_anterior=estado_anterior
        )
        
        # Exclui o item do banco de dados
        db(db.estoque.id == estoque_id).delete()
        db.commit()  # Confirma a exclusão no banco de dados
        
        # Mensagem de sucesso e redirecionamento
        response.flash = 'Item excluído com sucesso!'
        redirect(URL('index'))
    
    except Exception as e:
        # Caso ocorra algum erro, exibe uma mensagem para o usuário
        response.flash = f'Ocorreu um erro ao excluir o item: {str(e)}'
        redirect(URL('index'))




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