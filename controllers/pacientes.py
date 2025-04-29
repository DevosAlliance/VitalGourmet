import json
from gluon import current
from datetime import datetime, timedelta, date
import logging
from decimal import Decimal
import datetime
from io import StringIO
from gluon.contrib.pymysql.err import IntegrityError

@auth.requires(lambda: any(auth.has_membership(role) for role in ['Gestor', 'Recepção', 'Colaborador', 'Administrador']))
def index():
    # Parâmetros de filtro
    status_selecionado = request.vars.status or 'Ativo'
    nome_filtro = request.vars.nome or ''
    cpf_filtro = request.vars.cpf or ''

    # Parâmetros de paginação
    page = int(request.vars.page or 1)
    items_per_page = 10
    start = (page - 1) * items_per_page

    # Query com filtros
    query = (db.auth_user.user_type.belongs(
                db(db.user_type.name.belongs(['Paciente', 'Paciente Convenio', 'Paciente Particular'])).select(db.user_type.id))
            & (db.auth_user.status == status_selecionado))

    if nome_filtro:
        query &= db.auth_user.first_name.contains(nome_filtro)

    if cpf_filtro:
        query &= db.auth_user.cpf.contains(cpf_filtro)

    # Seleciona pacientes com limite e contagem total
    total_items = db(query).count()
    pacientes = db(query).select(
        db.auth_user.birth_date, 
        db.auth_user.id, 
        db.auth_user.first_name, 
        db.auth_user.cpf, 
        db.auth_user.status,
        limitby=(start, start + items_per_page)
    )

    total_pages = (total_items + items_per_page - 1) // items_per_page

    # Contagem de pacientes ativos, inativos e total
    total_ativos = db(
        (db.auth_user.user_type.belongs(
            db(db.user_type.name.belongs(['Paciente', 'Paciente Convenio', 'Paciente Particular'])).select(db.user_type.id)))
        & (db.auth_user.status == 'Ativo')
    ).count()

    total_inativos = db(
        (db.auth_user.user_type.belongs(
            db(db.user_type.name.belongs(['Paciente', 'Paciente Convenio', 'Paciente Particular'])).select(db.user_type.id)))
        & (db.auth_user.status == 'Inativo')
    ).count()

    total_geral = total_ativos + total_inativos

    return dict(
        pacientes=pacientes, 
        status_selecionado=status_selecionado, 
        nome_filtro=nome_filtro, 
        cpf_filtro=cpf_filtro,
        page=page, 
        total_pages=total_pages,
        total_ativos=total_ativos,
        total_inativos=total_inativos,
        total_geral=total_geral
    )


@auth.requires_login()
def cadastrar_paciente():
    app_name = request.application
    
    # Buscar tipos de paciente da categoria "Pacientes"
    tipos_paciente = get_tipos_por_categoria("Pacientes")
    
    return dict(app_name=app_name, tipos_paciente=tipos_paciente)

@auth.requires_login()
def api_cadastrar_paciente():
    """
    API para cadastrar um novo paciente com validações avançadas e mensagens amigáveis.
    """
    if request.env.request_method != 'POST':
        return response.json({'status': 'error', 'message': 'Método inválido. Use POST.'})

    try:
        dados = request.post_vars

        # Validação dos campos obrigatórios
        campos_obrigatorios = ['first_name', 'cpf', 'birth_date', 'user_type']
        faltantes = [campo for campo in campos_obrigatorios if not dados.get(campo)]
        if faltantes:
            return response.json({
                'status': 'error',
                'message': f'Campos obrigatórios ausentes: {", ".join(faltantes)}'
            })

        # Normalizar e validar CPF
        cpf = dados.cpf.replace('.', '').replace('-', '').strip()
        if len(cpf) != 11 or not cpf.isdigit():
            return response.json({
                'status': 'error',
                'message': 'CPF inválido. Certifique-se de inserir um CPF com 11 dígitos numéricos.'
            })

        # Verificar duplicidade de CPF
        if db(db.auth_user.cpf == cpf).count() > 0:
            return response.json({
                'status': 'error',
                'message': 'CPF já cadastrado. Por favor, verifique e tente novamente.'
            })

        # Validar o tipo de usuário
        tipo_usuario = db.user_type(dados.user_type)
        if not tipo_usuario:
            return response.json({
                'status': 'error',
                'message': 'Tipo de paciente inválido. Por favor, selecione um tipo de paciente válido.'
            })

        # Mapeamento automático de setor com base no tipo de usuário
        setor_por_tipo = {
            'Paciente': 21,
            'Paciente Convenio': 22,
            'Acompanhante': 23
        }
        setor_id = setor_por_tipo.get(tipo_usuario.name)

        # Inserir novo paciente no banco de dados
        user_id = db.auth_user.insert(
            first_name=dados.first_name.strip(),
            cpf=cpf,
            birth_date=dados.birth_date,
            user_type=dados.user_type,
            setor_id=setor_id,
            room=dados.get('room'),
            observations=dados.get('observations')
        )
        db.commit()

        return response.json({
            'status': 'success',
            'message': f'Paciente {dados.first_name} cadastrado com sucesso!',
            'user_id': user_id
        })

    except Exception as e:
        return response.json({'status': 'error', 'message': f'Ocorreu um erro inesperado: {str(e)}'})


@auth.requires(lambda: any(auth.has_membership(role) for role in ['Gestor', 'Colaborador', 'Administrador']))
def editar_paciente():
    app_name = request.application
    paciente_id = request.args(0) or redirect(URL('index'))

    # Busca o paciente no banco de dados
    paciente = db.auth_user(paciente_id) or redirect(URL('index'))

    # Busca os tipos de paciente da categoria "Pacientes" usando a nova estrutura
    categoria_pacientes = db(db.categoria_usuario.nome == 'Pacientes').select().first()
    
    if not categoria_pacientes:
        session.flash = 'Erro: Categoria de Pacientes não encontrada no sistema.'
        redirect(URL('index'))
    
    # Busca relacionamentos desta categoria
    relacionamentos = db(db.categoria_tipo_usuario.categoria_id == categoria_pacientes.id).select(
        db.categoria_tipo_usuario.tipo_id
    )
    
    # Extrai os IDs dos tipos
    tipo_ids = [r.tipo_id for r in relacionamentos]
    
    # Busca os tipos de usuário para pacientes
    user_type_options = db(db.user_type.id.belongs(tipo_ids)).select(
        orderby=db.user_type.name
    )
    
    if not user_type_options:
        session.flash = 'Erro: Não há tipos de pacientes configurados no sistema.'
        redirect(URL('index'))

    # Captura o estado anterior do paciente
    estado_anterior = {
        'nome': paciente.first_name,
        'tipo': paciente.user_type,
        'data_nascimento': paciente.birth_date,
        'cpf': paciente.cpf,
        'quarto': paciente.room,
    }

    if request.post_vars:
        try:
            # Atualiza o paciente
            paciente.update_record(
                first_name=request.post_vars.first_name,
                cpf=request.post_vars.cpf,
                birth_date=request.post_vars.birth_date,
                user_type=request.post_vars.user_type,
                room=request.post_vars.room,
                observations=request.post_vars.observations,
            )

            # Atualiza o grupo do paciente
            auth.del_membership(user_id=paciente_id)
            auth.add_membership(request.post_vars.user_type, paciente_id)

            # Registra a edição no log
            registrar_log(entidade='Paciente', registro_id=paciente_id, acao='edição', estado_anterior=estado_anterior)

            db.commit()

            response.flash = 'Paciente atualizado com sucesso!'
            redirect(URL('index'))
        except HTTP as e:
            if e.status == 303:
                session.flash = f'Paciente atualizado com sucesso!'
                redirect(URL('index'))
            else:
                db.rollback()
                session.flash = f'Erro ao atualizar paciente: {str(e)}'
                redirect(URL('index'))

        except Exception as e:
            db.rollback()
            session.flash = f'Erro ao atualizar paciente: {str(e)}'
            redirect(URL('index'))

    return dict(paciente=paciente, user_type_options=user_type_options, paciente_id=paciente_id, app_name=app_name)



@auth.requires(lambda: any(auth.has_membership(role) for role in ['Gestor', 'Colaborador', 'Administrador']))
def vincular_acompanhante():
    paciente_id = request.args(0) or redirect(URL('index'))
    paciente = db.auth_user(paciente_id) or redirect(URL('index'))

    def limpar_cpf(cpf):
        """Remove todos os caracteres não numéricos do CPF"""
        return ''.join(c for c in str(cpf) if c.isdigit())

    # Excluir acompanhante
    if 'delete_acompanhante_id' in request.vars:
        acompanhante_id = request.vars.delete_acompanhante_id
        db(db.acompanhante_vinculo.acompanhante_id == acompanhante_id).delete()
        db(db.auth_user.id == acompanhante_id).delete()
        session.flash = f'Acompanhante excluído com sucesso!'
        redirect(URL('vincular_acompanhante', args=[paciente_id]))

    # Cadastro de acompanhantes
    if request.env.request_method == 'POST':
        nome_acompanhantes = request.post_vars.getlist('nomeAcompanhante[]')
        cpf_acompanhantes = request.post_vars.getlist('cpfAcompanhante[]')
        data_nascimento_acompanhantes = request.post_vars.getlist('dataNascimentoAcompanhante[]')

        cpfs_duplicados = []
        sucesso = False

        for nome, cpf, data_nascimento in zip(nome_acompanhantes, cpf_acompanhantes, data_nascimento_acompanhantes):
            cpf_limpo = limpar_cpf(cpf)

            # Validação básica de CPF
            if len(cpf_limpo) != 11 or not cpf_limpo.isdigit():
                session.flash = f"O CPF '{cpf}' é inválido. Verifique e tente novamente."
                continue

            # Verificar se o CPF já existe
            existing_user = db(db.auth_user.cpf == cpf_limpo).select().first()
            if existing_user:
                cpfs_duplicados.append(cpf)
                continue

            # Gerar senha inicial
            senha_inicial = f"{cpf_limpo[-4:]}{data_nascimento.split('-')[0]}"

            # Inserir novo acompanhante
            try:
                acompanhante_id = db.auth_user.insert(
                    first_name=nome.strip(),
                    cpf=cpf_limpo,
                    birth_date=data_nascimento,
                    user_type=db(db.user_type.name == 'Acompanhante').select().first().id,
                    setor_id=23,
                    password=db.auth_user.password.validate(senha_inicial)[0],
                    email=f"{cpf_limpo}@temp.com"
                )

                # Vincular acompanhante ao paciente
                db.acompanhante_vinculo.insert(
                    paciente_id=paciente_id,
                    acompanhante_id=acompanhante_id
                )

                # Adicionar o acompanhante ao grupo correto
                auth.add_membership('Acompanhante', acompanhante_id)

                sucesso = True

            except Exception as e:
                session.flash = f"Ocorreu um erro ao cadastrar o acompanhante '{nome}': {e}"
                continue

        # Exibir mensagens apropriadas
        if cpfs_duplicados:
            session.flash = f"Os seguintes CPFs já estão cadastrados: {', '.join(cpfs_duplicados)}"

        if sucesso:
            session.flash = "Acompanhante(s) vinculado(s) com sucesso!"

        # Redirecionar após o processamento
        redirect(URL('vincular_acompanhante', args=[paciente_id]))

    # Listar vínculos existentes
    vinculos = db(db.acompanhante_vinculo.paciente_id == paciente_id).select(
        join=db.auth_user.on(db.acompanhante_vinculo.acompanhante_id == db.auth_user.id)
    )

    return dict(paciente=paciente, vinculos=vinculos)




# Consulta dos acompanhantes de um paciente específico
def ver_acompanhantes():
    paciente_id = request.args(0)
    acompanhantes = db(db.acompanhante.paciente_id == paciente_id).select()
    return dict(acompanhantes=acompanhantes)


@auth.requires_login()
def excluir_paciente():
    try:
        paciente_id = request.args(0, cast=int)

        # Buscando o paciente na tabela de usuários (auth_user)
        paciente = db((db.auth_user.id == paciente_id) & (db.auth_user.user_type == db(db.user_type.name == 'Paciente').select().first().id)).select().first()

        # Captura o estado anterior do colaborador antes da edição
        estado_anterior = {
            'nome': paciente.first_name,
            'tipo': paciente.user_type,
            'data_nascimento': paciente.birth_date,
            'cpf': paciente.cpf,
            'Quarto': paciente.room,
        }

        registrar_log(entidade='Paciente', registro_id=paciente_id, acao='edicao', estado_anterior=estado_anterior)

        if paciente:
            # Excluindo o paciente
            db(db.auth_user.id == paciente_id).delete()
            db.commit()
            response.flash = "Paciente excluído com sucesso!"
        else:
            response.flash = "Paciente não encontrado ou o usuário não é um paciente."
    except Exception as e:
        response.flash = f"Erro ao excluir o paciente: {e}"

    redirect(URL('index'))  # Ajuste o nome da função de redirecionamento conforme necessário

@auth.requires(lambda: any(auth.has_membership(role) for role in ['Gestor', 'Recepção', 'Colaborador', 'Administrador']))
def alterar_status_paciente():
    paciente_id = request.args(0, cast=int)
    paciente = db.auth_user(paciente_id)

    if not paciente:
        session.flash = "Paciente não encontrado."
        redirect(URL('index'))

    # Alternar entre "Ativo" e "Inativo"
    novo_status = 'Inativo' if paciente.status == 'Ativo' else 'Ativo'

    # Atualizar o status do paciente
    paciente.update_record(status=novo_status)

    # Atualizar o status dos acompanhantes vinculados
    acompanhantes = db(db.acompanhante_vinculo.paciente_id == paciente_id).select()
    for acompanhante in acompanhantes:
        db.auth_user(acompanhante.acompanhante_id).update_record(status=novo_status)

    db.commit()

    session.flash = f"Status do paciente e seus acompanhantes atualizado para {novo_status}."
    redirect(URL('index'))

@auth.requires(lambda: any(auth.has_membership(role) for role in ['Gestor',  'Administrador']))
def excluir_paciente():
    paciente_id = request.args(0) or redirect(URL('index'))

    # Verifica se o colaborador existe
    paciente = db.auth_user(paciente_id) or redirect(URL('index'))

    # Captura o estado anterior do colaborador antes da edição
    estado_anterior = {
        'nome': paciente.first_name,
        'tipo': paciente.user_type,
        'data_nascimento': paciente.birth_date,
        'cpf': paciente.cpf,
        'Quarto': paciente.room,
    }

    registrar_log(entidade='Paciente', registro_id=paciente_id, acao='edicao', estado_anterior=estado_anterior)


    try:
        # Exclui o colaborador
        db(db.auth_user.id == colaborador_id).delete()
        db.commit()
        response.flash = 'Colaborador excluído com sucesso!'
    except Exception as e:
        response.flash = f'Erro ao excluir o colaborador: {str(e)}'
        db.rollback()

    # Redireciona para a lista de colaboradores após a exclusão
    redirect(URL('listar_colaboradores'))



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