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
        
        # Log da exclusão antes de excluir
        acompanhante_info = db.auth_user(acompanhante_id)
        if acompanhante_info:
            db.log_sistema.insert(
                user_id=auth.user.id,
                entidade='acompanhante_vinculo',
                acao='exclusao',
                registro_id=acompanhante_id,
                observacao=json.dumps({
                    'acao': 'exclusao_acompanhante',
                    'paciente_id': paciente_id,
                    'acompanhante_nome': acompanhante_info.first_name,
                    'acompanhante_cpf': acompanhante_info.cpf
                })
            )
        
        # Excluir vinculo e usuário
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
                # Buscar o setor "Acompanhante" - se não existir, usar um padrão
                setor_acompanhante = db(db.setor.name == 'Acompanhante').select().first()
                setor_id = setor_acompanhante.id if setor_acompanhante else 23  # fallback para ID 23

                acompanhante_id = db.auth_user.insert(
                    first_name=nome.strip(),
                    cpf=cpf_limpo,
                    birth_date=data_nascimento,
                    user_type=db(db.user_type.name == 'Acompanhante').select().first().id,
                    setor_id=setor_id,
                    password=db.auth_user.password.validate(senha_inicial)[0],
                    email=f"{cpf_limpo}@temp.com",
                    status='Ativo'  # Garantir que o acompanhante está ativo
                )

                # Vincular acompanhante ao paciente
                db.acompanhante_vinculo.insert(
                    paciente_id=paciente_id,
                    acompanhante_id=acompanhante_id
                )

                # Adicionar o acompanhante ao grupo correto
                auth.add_membership('Acompanhante', acompanhante_id)

                # Log do cadastro
                db.log_sistema.insert(
                    user_id=auth.user.id,
                    entidade='acompanhante_vinculo',
                    acao='edicao',
                    registro_id=acompanhante_id,
                    observacao=json.dumps({
                        'acao': 'cadastro_acompanhante',
                        'paciente_id': paciente_id,
                        'acompanhante_nome': nome.strip(),
                        'acompanhante_cpf': cpf_limpo
                    })
                )

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

    # Listar vínculos existentes com ordenação
    vinculos = db(db.acompanhante_vinculo.paciente_id == paciente_id).select(
        join=db.auth_user.on(db.acompanhante_vinculo.acompanhante_id == db.auth_user.id),
        orderby=db.acompanhante_vinculo.id  # Ordena pela ordem de criação do vínculo
    )

    return dict(paciente=paciente, vinculos=vinculos)

def api_info_acompanhante():
    """
    Retorna informações de um acompanhante e seu paciente vinculado
    """
    try:
        acompanhante_id = request.vars.get('id') or request.args(0)
        
        if not acompanhante_id:
            raise ValueError("ID do acompanhante não fornecido.")
            
        # Buscar acompanhante e seu vínculo
        vinculo = db((db.acompanhante_vinculo.acompanhante_id == acompanhante_id) &
                    (db.auth_user.id == db.acompanhante_vinculo.acompanhante_id)).select(
            db.auth_user.ALL,
            db.acompanhante_vinculo.ALL,
            join=db.auth_user.on(db.acompanhante_vinculo.acompanhante_id == db.auth_user.id)
        ).first()
        
        if not vinculo:
            raise ValueError("Acompanhante não encontrado ou não está vinculado a nenhum paciente.")
            
        # Buscar dados do paciente
        paciente = db.auth_user(vinculo.acompanhante_vinculo.paciente_id)
        if not paciente:
            raise ValueError("Paciente vinculado não encontrado.")
            
        # Calcular posição do acompanhante (número sequencial)
        vinculos_paciente = db(db.acompanhante_vinculo.paciente_id == paciente.id).select(
            orderby=db.acompanhante_vinculo.id
        )
        
        numero_acompanhante = None
        for i, v in enumerate(vinculos_paciente, 1):
            if v.acompanhante_id == int(acompanhante_id):
                numero_acompanhante = i
                break
        
        return response.json({
            'status': 'success',
            'acompanhante': {
                'id': vinculo.auth_user.id,
                'nome': vinculo.auth_user.first_name,
                'cpf': vinculo.auth_user.cpf,
                'birth_date': vinculo.auth_user.birth_date.isoformat() if vinculo.auth_user.birth_date else None,
                'numero': numero_acompanhante
            },
            'paciente': {
                'id': paciente.id,
                'nome': paciente.first_name,
                'cpf': paciente.cpf,
                'tipo': db.user_type[paciente.user_type].name if paciente.user_type else None
            }
        })
        
    except Exception as e:
        return response.json({
            'status': 'error',
            'message': str(e)
        })




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



    # 2. Função para verificar se o colaborador pode solicitar refeição para pacientes

def pode_solicitar_para_paciente():
    """
    Verifica se o usuário logado tem permissão para solicitar refeições para pacientes
    """
    if not auth.user:
        return False
    
    # Tipos de usuário que podem solicitar refeições para pacientes
    tipos_permitidos = ['Gestor', 'Recepção', 'Colaborador', 'Administrador', 'Enfermagem', 'Medico']
    
    # Verifica se o usuário tem um dos tipos permitidos
    user_type_name = db.user_type[auth.user.user_type].name if auth.user.user_type else None
    
    return user_type_name in tipos_permitidos

def api_verificar_permissao_solicitar():
    """
    API para verificar se o colaborador atual pode solicitar refeições para pacientes
    """
    try:
        pode_solicitar = pode_solicitar_para_paciente()
        user_info = {
            'nome': auth.user.first_name if auth.user else '',
            'setor': db.setor[auth.user.setor_id].name if auth.user and auth.user.setor_id else 'Sem setor'
        }
        
        return response.json({
            'status': 'success',
            'pode_solicitar': pode_solicitar,
            'colaborador': user_info
        })
    except Exception as e:
        return response.json({
            'status': 'error',
            'message': str(e)
        })

def api_registrar_solicitacao_refeicao():
    if request.env.request_method != 'POST':
        return response.json({'status': 'error', 'message': 'Método inválido. Use POST.'})
    
    try:
        # Verificar se é uma solicitação via JSON (do frontend) ou form data
        if request.body:
            dados = json.loads(request.body.read().decode('utf-8'))
            solicitante_id = dados.get('solicitante_id')
            prato_id = int(dados.get('pratoid'))
            quantidade_solicitada = int(dados.get('quantidade'))
            descricao = dados.get('descricao', None)
            status = dados.get('status', 'Pendente')
            # Novo campo para identificar se é para acompanhante
            is_para_acompanhante = dados.get('is_para_acompanhante', False)
            acompanhante_id = dados.get('acompanhante_id', None)
        else:
            # Fallback para form data
            solicitante_id = request.post_vars.get('solicitante_id')
            prato_id = int(request.post_vars.get('pratoid'))
            quantidade_solicitada = int(request.post_vars.get('quantidade'))
            descricao = request.post_vars.get('descricao', None)
            status = request.post_vars.get('status', 'Pendente')
            is_para_acompanhante = request.post_vars.get('is_para_acompanhante', False)
            acompanhante_id = request.post_vars.get('acompanhante_id', None)

        # Se não foi fornecido solicitante_id, usar o usuário logado
        if not solicitante_id:
            solicitante_id = auth.user.id if auth.user else None
            
        if not solicitante_id:
            raise ValueError("Usuário não identificado.")

        # Verificar se o usuário logado pode fazer solicitações para outros usuários
        is_solicitacao_para_outro = str(solicitante_id) != str(auth.user.id if auth.user else '')
        
        if is_solicitacao_para_outro and not pode_solicitar_para_paciente():
            raise ValueError("Você não tem permissão para solicitar refeições para outros usuários.")

        # Se for para acompanhante, verificar se o acompanhante existe e está vinculado ao paciente
        if is_para_acompanhante and acompanhante_id:
            vinculo_acompanhante = db(
                (db.acompanhante_vinculo.acompanhante_id == acompanhante_id) &
                (db.acompanhante_vinculo.paciente_id == solicitante_id)
            ).select().first()
            
            if not vinculo_acompanhante:
                raise ValueError("Acompanhante não está vinculado ao paciente especificado.")

        hoje = datetime.now()

        # Verifica se o prato existe
        prato = db(db.cardapio.id == prato_id).select(
            db.cardapio.ALL,
            db.horario_refeicoes.pedido_fim,
            left=[
                db.horario_refeicoes.on(db.cardapio.tipo == db.horario_refeicoes.refeicao)
            ]
        ).first()

        if not prato:
            raise ValueError("O prato especificado não existe.")

        # Se for para acompanhante, usar o ID do acompanhante para validação, 
        # mas o pedido será registrado no nome do paciente
        validador_id = acompanhante_id if is_para_acompanhante and acompanhante_id else solicitante_id
        
        # Inicializa classes de validação e gratuidade
        validador = ValidadorUsuario(validador_id, db)
        gerenciador = GerenciadorGratuidade(validador, db)

        # Verifica se o usuário pode solicitar o prato
        if not validador.pode_solicitar_prato(prato.cardapio):
            usuario_nome = "o acompanhante" if is_para_acompanhante else "o usuário"
            raise ValueError(f"{usuario_nome} não tem permissão para solicitar este prato.")

        # Calcula preço/verifica gratuidade
        resultado_gratuidade = gerenciador.calcular_gratuidade(prato.cardapio, quantidade_solicitada)

        # Se não foi fornecida descrição e é uma solicitação para outro usuário, criar descrição automática
        if not descricao and is_solicitacao_para_outro:
            colaborador_nome = auth.user.first_name if auth.user else 'Colaborador'
            colaborador_setor = db.setor[auth.user.setor_id].name if auth.user and auth.user.setor_id else 'Sem setor'
            
            if is_para_acompanhante and acompanhante_id:
                # Buscar informações do acompanhante
                acompanhante_info = db.auth_user(acompanhante_id)
                paciente_info = db.auth_user(solicitante_id)
                
                # Calcular número do acompanhante
                vinculos_paciente = db(db.acompanhante_vinculo.paciente_id == solicitante_id).select(
                    orderby=db.acompanhante_vinculo.id
                )
                numero_acompanhante = None
                for i, v in enumerate(vinculos_paciente, 1):
                    if v.acompanhante_id == int(acompanhante_id):
                        numero_acompanhante = i
                        break
                
                if acompanhante_info and paciente_info and numero_acompanhante:
                    descricao = f"Pedido pelo colaborador {colaborador_nome} ({colaborador_setor}) para o acompanhante nº {numero_acompanhante} do paciente {paciente_info.first_name}"
                else:
                    descricao = f"Pedido pelo colaborador {colaborador_nome} ({colaborador_setor}) para acompanhante do paciente"
            else:
                paciente_nome = db.auth_user[solicitante_id].first_name if db.auth_user[solicitante_id] else 'Paciente'
                descricao = f"Pedido pelo colaborador {colaborador_nome} ({colaborador_setor}) para o paciente {paciente_nome}"
        elif not descricao:
            descricao = validador.obter_nome_observacao_pedido()

        # O pedido sempre fica no nome do paciente (solicitante_id), mesmo quando é para acompanhante
        dict_solicitacao = {
            'solicitante_id': validador.solicitante_real_id,  # Sempre será o paciente
            'is_acompanhante': validador.is_acompanhante,
            'prato_id': prato_id,
            'preco': resultado_gratuidade['preco_total'],
            'quantidade_solicitada': quantidade_solicitada,
            'descricao': descricao,
            'status': status
        }

        # Verificar se é café da manhã e se passou do horário
        if prato.cardapio.tipo == 'Café da Manhã' and \
            prato.horario_refeicoes.pedido_fim < hoje.time():
            dict_solicitacao['data_solicitacao'] = (hoje + timedelta(days=1)).date()

        # Commit
        solicitacao_id = db.solicitacao_refeicao.insert(**dict_solicitacao)

        # Atualiza o saldo (sempre do paciente)
        _atualizar_saldo_usuario(validador.solicitante_real_id, resultado_gratuidade['preco_total'])

        # Log da ação se foi feita por um colaborador
        if is_solicitacao_para_outro:
            log_observacao = {
                'acao': 'solicitacao_por_colaborador_para_acompanhante' if is_para_acompanhante else 'solicitacao_por_colaborador',
                'paciente_id': solicitante_id,
                'prato_id': prato_id,
                'quantidade': quantidade_solicitada,
                'valor': float(resultado_gratuidade['preco_total'])
            }
            
            if is_para_acompanhante and acompanhante_id:
                log_observacao['acompanhante_id'] = acompanhante_id
            
            db.log_sistema.insert(
                user_id=auth.user.id,
                entidade='solicitacao_refeicao',
                acao='edicao',
                registro_id=solicitacao_id,
                observacao=json.dumps(log_observacao)
            )

        db.commit()
        
        return response.json({
            'status': 'success', 
            'message': 'Solicitação de refeição registrada com sucesso!', 
            'solicitacao_id': solicitacao_id,
            'is_solicitacao_colaborador': is_solicitacao_para_outro,
            'is_para_acompanhante': is_para_acompanhante
        })

    except Exception as e:
        db.rollback()
        return response.json({'status': 'error', 'message': str(e)})


# 4. Função auxiliar para validar acompanhante
def validar_acompanhante(acompanhante_id, paciente_id=None):
    """
    Valida se o usuário é um acompanhante válido e, opcionalmente, 
    se está vinculado a um paciente específico
    """
    try:
        acompanhante = db.auth_user(acompanhante_id)
        if not acompanhante:
            return False
            
        # Verifica se é do tipo "Acompanhante"
        user_type_name = db.user_type[acompanhante.user_type].name if acompanhante.user_type else None
        if user_type_name != 'Acompanhante':
            return False
            
        # Se foi especificado um paciente, verifica o vínculo
        if paciente_id:
            vinculo = db((db.acompanhante_vinculo.acompanhante_id == acompanhante_id) &
                        (db.acompanhante_vinculo.paciente_id == paciente_id)).select().first()
            return bool(vinculo)
            
        # Se não foi especificado paciente, apenas verifica se tem algum vínculo
        vinculo = db(db.acompanhante_vinculo.acompanhante_id == acompanhante_id).select().first()
        return bool(vinculo)
        
    except:
        return False

def api_listar_acompanhantes_paciente():
    """
    Lista todos os acompanhantes vinculados a um paciente específico
    """
    try:
        paciente_id = request.vars.get('paciente_id') or request.args(0)
        
        if not paciente_id:
            raise ValueError("ID do paciente não fornecido.")
            
        if not validar_usuario_paciente(paciente_id):
            raise ValueError("Usuário não é um paciente válido.")
            
        # Buscar acompanhantes
        vinculos = db(db.acompanhante_vinculo.paciente_id == paciente_id).select(
            db.auth_user.ALL,
            db.acompanhante_vinculo.ALL,
            join=db.auth_user.on(db.acompanhante_vinculo.acompanhante_id == db.auth_user.id),
            orderby=db.acompanhante_vinculo.id
        )
        
        acompanhantes = []
        for i, vinculo in enumerate(vinculos, 1):
            acompanhantes.append({
                'id': vinculo.auth_user.id,
                'nome': vinculo.auth_user.first_name,
                'cpf': vinculo.auth_user.cpf,
                'birth_date': vinculo.auth_user.birth_date.isoformat() if vinculo.auth_user.birth_date else None,
                'numero': i  # Número sequencial do acompanhante
            })
        
        return response.json({
            'status': 'success',
            'paciente_id': paciente_id,
            'acompanhantes': acompanhantes,
            'total': len(acompanhantes)
        })
        
    except Exception as e:
        return response.json({
            'status': 'error',
            'message': str(e)
        })

def validar_usuario_paciente(usuario_id):
    """
    Valida se o usuário fornecido é realmente um paciente
    """
    try:
        usuario = db.auth_user[usuario_id]
        if not usuario:
            return False
            
        tipos_paciente = ['Paciente', 'Paciente Convenio', 'Paciente Particular']
        user_type_name = db.user_type[usuario.user_type].name if usuario.user_type else None
        
        return user_type_name in tipos_paciente and usuario.status == 'Ativo'
    except:
        return False

def api_info_paciente():
    """
    Retorna informações básicas de um paciente específico
    """
    try:
        paciente_id = request.vars.get('id') or request.args(0)
        
        if not paciente_id:
            raise ValueError("ID do paciente não fornecido.")
            
        if not validar_usuario_paciente(paciente_id):
            raise ValueError("Usuário não é um paciente válido.")
            
        paciente = db.auth_user[paciente_id]
        user_type = db.user_type[paciente.user_type]
        
        return response.json({
            'status': 'success',
            'paciente': {
                'id': paciente.id,
                'nome': paciente.first_name,
                'cpf': paciente.cpf,
                'tipo': user_type.name,
                'birth_date': paciente.birth_date.isoformat() if paciente.birth_date else None
            }
        })
        
    except Exception as e:
        return response.json({
            'status': 'error',
            'message': str(e)
        })