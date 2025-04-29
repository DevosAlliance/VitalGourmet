import json
from gluon import current
from datetime import datetime, timedelta, date
import logging
from decimal import Decimal
import datetime
from io import StringIO
from gluon.contrib.pymysql.err import IntegrityError

# Função para listar os colaboradores
@auth.requires(lambda: any(auth.has_membership(role) for role in ['Administrador', 'Gestor']))
def index():
    tipos_colaboradores = ['Hemodialise', 'Instrumentador', 'Gestor', 'Colaborador', 'Medico']
    nome_filtro = request.vars.nome or ''
    cpf_filtro = request.vars.cpf or ''
    setor_filtro = request.vars.setor_id or None
    pagina = int(request.vars.pagina or 1)
    registros_por_pagina = 10
    inicio = (pagina - 1) * registros_por_pagina
    fim = inicio + registros_por_pagina

    # Cache da lista de IDs dos tipos de colaboradores
    tipos_ids = cache.ram(
        'tipos_colaboradores_ids',
        lambda: [row.id for row in db(db.user_type.name.belongs(tipos_colaboradores)).select(db.user_type.id)],
        time_expire=60
    )

    # Filtro otimizado
    query = db.auth_user.user_type.belongs(tipos_ids)

    if nome_filtro:
        query &= db.auth_user.first_name.contains(nome_filtro)

    if cpf_filtro:
        query &= db.auth_user.cpf.contains(cpf_filtro)

    if setor_filtro:
        query &= (db.auth_user.setor_id == int(setor_filtro))

    # Aplicação da paginação
    total_colaboradores = db(query).count()
    colaboradores = db(query).select(
        db.auth_user.id, db.auth_user.first_name, db.auth_user.cpf, db.auth_user.setor_id,
        limitby=(inicio, fim)
    )

    # Cache da lista de setores
    setores = cache.ram('setores_lista', lambda: db(db.setor).select(), time_expire=300)

    return dict(
        colaboradores=colaboradores,
        setores=setores,
        nome_filtro=nome_filtro,
        cpf_filtro=cpf_filtro,
        setor_filtro=setor_filtro,
        pagina=pagina,
        total_colaboradores=total_colaboradores,
        registros_por_pagina=registros_por_pagina
    )

def diagnosticar_problema():
    resultados = {}
    
    # 1. Verificar se a tabela categoria_usuario existe
    try:
        categoria_usuario_existe = db(db.categoria_usuario.id > 0).count() >= 0
        resultados['categoria_usuario_existe'] = categoria_usuario_existe
    except Exception as e:
        resultados['categoria_usuario_existe'] = f"Erro: {str(e)}"
    
    # 2. Verificar se a tabela categoria_tipo_usuario existe
    try:
        categoria_tipo_usuario_existe = db(db.categoria_tipo_usuario.id > 0).count() >= 0
        resultados['categoria_tipo_usuario_existe'] = categoria_tipo_usuario_existe
    except Exception as e:
        resultados['categoria_tipo_usuario_existe'] = f"Erro: {str(e)}"
    
    # 3. Verificar categoria Colaboradores
    try:
        categoria_colaboradores = db(db.categoria_usuario.nome == 'Colaboradores').select().first()
        resultados['categoria_colaboradores'] = categoria_colaboradores is not None
        if categoria_colaboradores:
            resultados['id_categoria_colaboradores'] = categoria_colaboradores.id
    except Exception as e:
        resultados['categoria_colaboradores'] = f"Erro: {str(e)}"
    
    # 4. Verificar tipos de colaboradores
    try:
        tipos_colaboradores = ['Hemodiálise', 'Instrumentador', 'Gestor', 'Colaborador', 'Medico']
        tipos = db(db.user_type.name.belongs(tipos_colaboradores)).select()
        resultados['tipos_colaboradores_existem'] = len(tipos) > 0
        resultados['qtd_tipos_colaboradores'] = len(tipos)
        resultados['tipos_encontrados'] = [t.name for t in tipos]
    except Exception as e:
        resultados['tipos_colaboradores_existem'] = f"Erro: {str(e)}"
    
    # 5. Verificar associações na tabela categoria_tipo_usuario
    try:
        if categoria_colaboradores:
            associacoes = db(db.categoria_tipo_usuario.categoria_id == categoria_colaboradores.id).select()
            resultados['associacoes_existem'] = len(associacoes) > 0
            resultados['qtd_associacoes'] = len(associacoes)
            
            # Verificar cada tipo associado
            tipos_associados = []
            for assoc in associacoes:
                tipo = db.user_type(assoc.tipo_id)
                if tipo:
                    tipos_associados.append(tipo.name)
            resultados['tipos_associados'] = tipos_associados
    except Exception as e:
        resultados['associacoes_existem'] = f"Erro: {str(e)}"
    
    # 6. Verificar o código que está gerando o erro
    try:
        if categoria_colaboradores:
            # Repetir a lógica exata do controller que está falhando
            relacionamentos = db(db.categoria_tipo_usuario.categoria_id == categoria_colaboradores.id).select(
                db.categoria_tipo_usuario.tipo_id
            )
            tipo_ids = [r.tipo_id for r in relacionamentos]
            user_type_options = db(db.user_type.id.belongs(tipo_ids)).select(
                orderby=db.user_type.name
            )
            resultados['relacionamentos_encontrados'] = len(relacionamentos)
            resultados['tipo_ids_encontrados'] = tipo_ids
            resultados['user_type_options_encontrados'] = len(user_type_options)
    except Exception as e:
        resultados['codigo_erro'] = f"Erro: {str(e)}"
    
    return resultados


def corrigir_problema():
    # Forçar a criação da categoria Colaboradores
    categoria = db(db.categoria_usuario.nome.like('Colaboradores')).select().first()
    
    if not categoria:
        categoria_id = db.categoria_usuario.insert(
            nome='Colaboradores',
            descricao='Funcionários e colaboradores',
            cor='#28a745',
            ativo=True
        )
    else:
        categoria_id = categoria.id
    
    # Buscar tipos de colaboradores
    tipos_colaboradores = ['Hemodiálise', 'Instrumentador', 'Gestor', 'Colaborador', 'Medico', 'hemodialise']
    tipos = db(db.user_type.name.belongs(tipos_colaboradores)).select()
    
    # Forçar a associação de cada tipo à categoria
    quantidade_associacoes = 0
    for tipo in tipos:
        # Verificar se já existe a associação
        associacao = db((db.categoria_tipo_usuario.categoria_id == categoria_id) & 
                       (db.categoria_tipo_usuario.tipo_id == tipo.id)).select().first()
        
        # Se não existir, criar
        if not associacao:
            db.categoria_tipo_usuario.insert(
                categoria_id=categoria_id,
                tipo_id=tipo.id
            )
            quantidade_associacoes += 1
    
    db.commit()
    
    # Verificar se foram criadas associações
    associacoes = db(db.categoria_tipo_usuario.categoria_id == categoria_id).select()
    
    return {
        "categoria_id": categoria_id,
        "quantidade_tipos_encontrados": len(tipos),
        "nomes_tipos_encontrados": [t.name for t in tipos],
        "novas_associacoes_criadas": quantidade_associacoes,
        "total_associacoes": len(associacoes)
    }

@auth.requires(lambda: any(auth.has_membership(role) for role in ['Gestor', 'Administrador']))
def cadastrar_colaborador():
    app_name = request.application
    
    # Busca os tipos de colaborador da categoria "Colaboradores" usando a estrutura dinâmica
    categoria_colaboradores = db(db.categoria_usuario.nome == 'Colaboradores').select().first()
    
    if not categoria_colaboradores:
        session.flash = 'Erro: Categoria de Colaboradores não encontrada no sistema.'
        redirect(URL('index'))
    
    # Busca relacionamentos desta categoria
    relacionamentos = db(db.categoria_tipo_usuario.categoria_id == categoria_colaboradores.id).select(
        db.categoria_tipo_usuario.tipo_id
    )
    
    # Extrai os IDs dos tipos
    tipo_ids = [r.tipo_id for r in relacionamentos]
    
    # Busca os tipos de usuário para colaboradores
    user_type_options = db(db.user_type.id.belongs(tipo_ids)).select(
        orderby=db.user_type.name
    )
    
    if not user_type_options:
        session.flash = 'Erro: Não há tipos de colaboradores configurados no sistema.'
        redirect(URL('index'))
        
    # Busca todos os setores exceto o de pacientes
    setores = db(db.setor.name != 'Paciente').select()
    
    # Vamos criar um mapeamento de tipos para setores permitidos na tabela de configuração
    # Isso substituirá o objeto JavaScript hardcoded
    setores_por_tipo = {}
    
    # Buscar da tabela de configurações ou criar uma nova tabela específica
    try:
        config_setores = db(db.configuracoes.nome == 'setores_por_tipo_colaborador').select().first()
        if config_setores:
            setores_por_tipo = json.loads(config_setores.valor)
    except:
        # Caso não exista ainda, podemos inicializar com os valores atuais
        pass
    
    if request.post_vars:
        try:
            # Insere o colaborador no banco
            user_id = db.auth_user.insert(
                first_name=request.post_vars.first_name,
                cpf=request.post_vars.cpf,
                birth_date=request.post_vars.birth_date,
                email=request.post_vars.email,  
                password=db.auth_user.password.validate(request.post_vars.password)[0],
                setor_id=request.post_vars.setor_id,
                user_type=request.post_vars.user_type
            )

            # Adiciona o colaborador ao grupo correto
            auth.add_membership(request.post_vars.user_type, user_id)
            
            response.flash = 'Colaborador cadastrado com sucesso!'
            redirect(URL('index'))

        except IntegrityError as e:
            if 'cpf' in str(e):
                response.flash = 'Erro: Este CPF já está cadastrado no sistema.'
            else:
                response.flash = 'Erro ao cadastrar colaborador. Verifique os dados fornecidos.'

    return dict(
        user_type_options=user_type_options, 
        setores=setores, 
        setores_por_tipo=json.dumps(setores_por_tipo),
        app_name=app_name
    )

@auth.requires(lambda: any(auth.has_membership(role) for role in ['Gestor', 'Administrador']))
def editar_colaborador():
    app_name = request.application
    colaborador_id = request.args(0) or redirect(URL('index'))

    # Busca o colaborador no banco de dados
    colaborador = db.auth_user(colaborador_id) or redirect(URL('index'))

    # Busca os tipos de colaborador da categoria "Colaboradores" usando a estrutura dinâmica
    categoria_colaboradores = db(db.categoria_usuario.nome == 'Colaboradores').select().first()
    
    if not categoria_colaboradores:
        session.flash = 'Erro: Categoria de Colaboradores não encontrada no sistema.'
        redirect(URL('index'))
    
    # Busca relacionamentos desta categoria
    relacionamentos = db(db.categoria_tipo_usuario.categoria_id == categoria_colaboradores.id).select(
        db.categoria_tipo_usuario.tipo_id
    )
    
    # Extrai os IDs dos tipos
    tipo_ids = [r.tipo_id for r in relacionamentos]
    
    # Busca os tipos de usuário para colaboradores
    user_type_options = db(db.user_type.id.belongs(tipo_ids)).select(
        orderby=db.user_type.name
    )
    
    if not user_type_options:
        session.flash = 'Erro: Não há tipos de colaboradores configurados no sistema.'
        redirect(URL('index'))
        
    # Busca todos os setores exceto os setores de pacientes
    setores_permitidos = db(db.setor.name != 'Paciente').select()
    
    # Vamos buscar o mapeamento de tipos para setores permitidos
    setores_por_tipo = {}
    try:
        config_setores = db(db.configuracoes.nome == 'setores_por_tipo_colaborador').select().first()
        if config_setores:
            setores_por_tipo = json.loads(config_setores.valor)
    except:
        pass
    
    # Captura o estado anterior do colaborador
    estado_anterior = {
        'nome': colaborador.first_name,
        'Tipo': colaborador.user_type,
        'Setor': colaborador.setor_id,
        'Data de nascimento': colaborador.birth_date,
    }

    # Processar o formulário enviado
    if request.post_vars:
        try:
            # Atualiza o colaborador
            colaborador.update_record(
                first_name=request.post_vars.first_name,
                cpf=request.post_vars.cpf,
                birth_date=request.post_vars.birth_date,
                email=request.post_vars.email,
                password=db.auth_user.password.validate(request.post_vars.password)[0] if request.post_vars.password else colaborador.password,
                setor_id=request.post_vars.setor_id,
                user_type=request.post_vars.user_type
            )

            # Atualiza o grupo do colaborador
            auth.del_membership(user_id=colaborador_id)
            auth.add_membership(request.post_vars.user_type, colaborador_id)

            # Registra a edição no log com o estado anterior
            registrar_log(entidade='colaborador', registro_id=colaborador_id, acao='edição', estado_anterior=estado_anterior)

            db.commit()

            response.flash = 'Colaborador atualizado com sucesso!'
            redirect(URL('index'))
            
        except Exception as e:
            db.rollback()
            response.flash = f'Erro ao atualizar colaborador: {str(e)}'
            
    return dict(
        colaborador=colaborador, 
        user_type_options=user_type_options, 
        setores_permitidos=setores_permitidos, 
        colaborador_id=colaborador_id,
        setores_por_tipo=json.dumps(setores_por_tipo),
        app_name=app_name
    )
    

@auth.requires(lambda: any(auth.has_membership(role) for role in ['Gestor',  'Administrador']))
def excluir_colaborador():
    colaborador_id = request.args(0) or redirect(URL('index'))

    # Verifica se o colaborador existe
    colaborador = db.auth_user(colaborador_id) or redirect(URL('index'))

    # Captura o estado anterior do item antes da exclusão
    estado_anterior = {
        'nome': colaborador.first_name,
        'Tipo': colaborador.user_type,
        'Setor': colaborador.setor_id,
        'Data de nascimento': colaborador.birth_date,
    }

    # Registra a exclusão no log com o estado anterior
    registrar_log(entidade='colaborador', registro_id=colaborador_id, acao='exclusao', estado_anterior=estado_anterior)

    try:
        # Exclui o colaborador
        db(db.auth_user.id == colaborador_id).delete()
        db.commit()
        response.flash = 'Colaborador excluído com sucesso!'
    except Exception as e:
        response.flash = f'Erro ao excluir o colaborador: {str(e)}'
        db.rollback()

    # Redireciona para a lista de colaboradores após a exclusão
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