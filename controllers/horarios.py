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
    setor_filtro = request.vars.setor or ''
    refeicao_filtro = request.vars.refeicao or ''

    query = db.horario_refeicoes.id > 0

    if setor_filtro:
        query &= db.horario_refeicoes.tipo_usuario.contains(setor_filtro)

    if refeicao_filtro:
        query &= (db.horario_refeicoes.refeicao == refeicao_filtro)

    horarios = db(query).select()

    refeicoes = db(db.horario_refeicoes).select(db.horario_refeicoes.refeicao, distinct=True)
    setores = db(db.user_type.id > 0).select()

    return dict(horarios=horarios, setores=setores, refeicoes=refeicoes, setor_filtro=setor_filtro, refeicao_filtro=refeicao_filtro)

@auth.requires_login()
def cadastrar_horario_refeicao():
    # Inicializa `horario` como `None` para evitar erros na view
    horario = None

    tipos_usuario = db(db.user_type.id > 0).select()

    if request.env.request_method == 'POST':
        try:
            tipos_usuario = request.post_vars.getlist('tipos_usuario')  # Pega múltiplos tipos de usuário
            refeicao = request.post_vars.refeicao
            pedido_inicio = request.post_vars.pedido_inicio
            pedido_fim = request.post_vars.pedido_fim
            servido_inicio = request.post_vars.servido_inicio

            # Verifica se todos os campos obrigatórios estão preenchidos
            if not (tipos_usuario and refeicao and pedido_inicio and pedido_fim and servido_inicio):
                raise ValueError("Todos os campos são obrigatórios.")

            # Insere o novo horário de refeição no banco de dados
            horario_id = db.horario_refeicoes.insert(
                tipo_usuario=json.dumps(tipos_usuario),  # Armazena como JSON
                refeicao=refeicao,
                pedido_inicio=pedido_inicio,
                pedido_fim=pedido_fim,
                servido_inicio=servido_inicio
            )
            db.commit()
            response.flash = "Horário de refeição cadastrado com sucesso!"
            redirect(URL('horarios', 'index'))
        except Exception as e:
            db.rollback()
            response.flash = f"Erro ao cadastrar o horário: {e}"

    return dict(horario=horario, tipos_usuario=tipos_usuario)  # Passa `horario` como `None` e a lista de tipos de usuários para a view

@auth.requires_login()
def editar_horario_refeicao():
    horario_id = request.args(0) or redirect(URL('horarios', 'index'))
    horario = db.horario_refeicoes(horario_id) or redirect(URL('horarios', 'index'))


    if request.env.request_method == 'POST':
        try:
            tipos_usuario = request.post_vars.getlist('tipos_usuario')
            refeicao = request.post_vars.refeicao
            pedido_inicio = request.post_vars.pedido_inicio
            pedido_fim = request.post_vars.pedido_fim
            servido_inicio = request.post_vars.servido_inicio

            # Atualiza o horário de refeição no banco de dados
            horario.update_record(
                tipo_usuario=json.dumps(tipos_usuario),  # Armazena como JSON
                refeicao=refeicao,
                pedido_inicio=pedido_inicio,
                pedido_fim=pedido_fim,
                servido_inicio=servido_inicio
            )
            db.commit()
            response.flash = "Horário de refeição atualizado com sucesso!"
            redirect(URL('horarios', 'index'))
            
        except HTTP as e:
            if e.status == 303:
                session.flash = f'Horário atualizado com sucesso!'
                redirect(URL('index'))
            else:
                db.rollback()
                session.flash = f'Erro ao atualizar o horário: {str(e)}'
                redirect(URL('index'))

        except Exception as e:
            db.rollback()
            session.flash = f'Erro ao atualizar o horário: {str(e)}'
            redirect(URL('index'))
    
    # Função para buscar todos os tipos de usuário do banco de dados
    def get_all_user_types():
        # Busca todos os tipos de usuário do banco de dados
        user_types = db(db.user_type).select(db.user_type.name, orderby=db.user_type.name)
        # Converte para lista de nomes
        tipos = [ut.name for ut in user_types]
        return tipos
    
    # Usando cache para melhor performance
    tipos_usuario = cache.ram(
        'tipos_usuario_for_horarios',
        get_all_user_types,
        time_expire=300
    )

    return dict(horario=horario, tipos_usuario=tipos_usuario)

@auth.requires_login()
def excluir_horario_refeicao():
    horario_id = request.args(0) or redirect(URL('horarios', 'index'))
    try:
        db(db.horario_refeicoes.id == horario_id).delete()
        db.commit()
        response.flash = "Horário de refeição excluído com sucesso!"
    except Exception as e:
        db.rollback()
        response.flash = f"Erro ao excluir o horário: {e}"

    redirect(URL('horarios', 'index'))

