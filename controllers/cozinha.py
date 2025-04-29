import json
import logging
from datetime import datetime
from gluon import current
from decimal import Decimal
from io import StringIO
from gluon.contrib.pymysql.err import IntegrityError

# cozinha
@auth.requires(lambda: any(auth.has_membership(role) for role in ['Gestor', 'Colaborador', 'Administrador']))
def index():
    return dict()


# Controlador da API para retorno de solicitações de refeições filtradas
def api_gerenciar_pedidos():
    tipos_permitidos = ['Medico', 'Colaborador', 'Hemodialise', 'Gestor', 'Instrumentador', 'Administrador']

    tipos_ids = db(db.user_type.name.belongs(tipos_permitidos)).select(db.user_type.id)

    hoje = datetime.now()

    pedidos = db(
        (~db.solicitacao_refeicao.status.belongs(['Finalizado', 'Pago'])) &
        (~db.cardapio.tipo.belongs(['A La Carte', 'Livre', 'Bebidas'])) &
        (db.auth_user.user_type.belongs([tipo.id for tipo in tipos_ids])) &
        (
            (db.solicitacao_refeicao.data_solicitacao < hoje.date) |
            (
                (db.horario_refeicoes.servido_inicio <= hoje.time()) &
                (db.solicitacao_refeicao.data_solicitacao == hoje.date())
            )
        )
    ).select(
        db.solicitacao_refeicao.ALL,
        db.cardapio.nome,
        db.auth_user.first_name,
        db.auth_user.user_type,
        db.setor.name,
        left=[
            db.cardapio.on(db.solicitacao_refeicao.prato_id == db.cardapio.id),
            db.horario_refeicoes.on(db.cardapio.tipo == db.horario_refeicoes.refeicao),
            db.auth_user.on(db.solicitacao_refeicao.solicitante_id == db.auth_user.id),
            db.setor.on(db.auth_user.setor_id == db.setor.id)
        ],
        orderby=db.auth_user.first_name
    )

    resultado = []
    for pedido in pedidos:
        user_type_name = pedido.auth_user.user_type.name if pedido.auth_user.user_type else None

        resultado.append({
            'Solicitante': pedido.auth_user.first_name,
            'Setor': pedido.setor.name if pedido.setor else None,
            'Prato': pedido.cardapio.nome,
            'Quantidade': pedido.solicitacao_refeicao.quantidade_solicitada,
            'Preco': str(pedido.solicitacao_refeicao.preco),
            'Status': pedido.solicitacao_refeicao.status,
            'Tipo de Usuario': user_type_name
        })

    return response.json({'pedidos': resultado})


#  meus pedidos
@auth.requires_login()
def impressao():
    return dict()


def api_listar_pedidos():
    try:
        # Definir os tipos de usuário
        tipos_normais = ['Paciente', 'Paciente Convenio', 'Acompanhante', 'Hemodialise']
        tipos_filtrados = ['Medico', 'Colaborador', 'Gestor', 'Administrador', 'Instrumentador', 'Colaborador']

        # Obter os IDs dos tipos normais e filtrados
        tipos_normais_ids = [tipo.id for tipo in db(db.user_type.name.belongs(tipos_normais)).select(db.user_type.id)]
        tipos_filtrados_ids = [tipo.id for tipo in db(db.user_type.name.belongs(tipos_filtrados)).select(db.user_type.id)]

        if not tipos_normais_ids or not tipos_filtrados_ids:
            raise ValueError("IDs de tipos de usuário não encontrados.")

        # Obter o ID do setor "Colaborador Hemodialise"
        setor_colaborador_hemodialise = db(db.setor.name == "Colaborador Hemodialise").select(db.setor.id).first()
        setor_colaborador_hemodialise_id = setor_colaborador_hemodialise.id if setor_colaborador_hemodialise else None

        hoje = datetime.now()

        # 1. Pedidos de tipos de pratos sempre visíveis (A La Carte, Livre e Bebidas)
        pedidos_livres = db(
            (~db.solicitacao_refeicao.status.belongs(['Finalizado', 'Pago']))&
            (db.cardapio.tipo.belongs(['A La Carte', 'Livre', 'Bebidas'])) &
            (
                (db.solicitacao_refeicao.data_solicitacao < hoje.date) |
                (
                    (db.horario_refeicoes.servido_inicio <= hoje.time()) &
                    (db.solicitacao_refeicao.data_solicitacao == hoje.date())
                )
            )
        ).select(
            db.solicitacao_refeicao.ALL,
            db.cardapio.foto_do_prato,
            db.cardapio.nome,
            db.auth_user.first_name,
            db.auth_user.room,
            db.auth_user.observations,
            db.auth_user.user_type,
            db.setor.name,
            left=[
                db.cardapio.on(db.solicitacao_refeicao.prato_id == db.cardapio.id),
                db.horario_refeicoes.on(db.cardapio.tipo == db.horario_refeicoes.refeicao),
                db.auth_user.on(db.solicitacao_refeicao.solicitante_id == db.auth_user.id),
                db.setor.on(db.auth_user.setor_id == db.setor.id)
            ]
        )

        # 2. Pedidos para tipos normais (qualquer tipo de prato)
        pedidos_normais = db(
            (~db.solicitacao_refeicao.status.belongs(['Finalizado', 'Pago'])) &
            (db.auth_user.user_type.belongs(tipos_normais_ids)) &
            (
                (db.solicitacao_refeicao.data_solicitacao < hoje.date) |
                (
                    (db.horario_refeicoes.servido_inicio <= hoje.time()) &
                    (db.solicitacao_refeicao.data_solicitacao == hoje.date())
                )
            ) &
            ~((db.auth_user.user_type == db(db.user_type.name == 'Hemodialise').select(db.user_type.id).first().id) &
              (db.auth_user.setor_id == setor_colaborador_hemodialise_id))
        ).select(
            db.solicitacao_refeicao.ALL,
            db.cardapio.foto_do_prato,
            db.cardapio.nome,
            db.auth_user.first_name,
            db.auth_user.room,
            db.auth_user.observations,
            db.auth_user.user_type,
            db.setor.name,
            left=[
                db.cardapio.on(db.solicitacao_refeicao.prato_id == db.cardapio.id),
                db.horario_refeicoes.on(db.cardapio.tipo == db.horario_refeicoes.refeicao),
                db.auth_user.on(db.solicitacao_refeicao.solicitante_id == db.auth_user.id),
                db.setor.on(db.auth_user.setor_id == db.setor.id)
            ]
        )

        # # 3. Pedidos para tipos filtrados (somente A La Carte, Livre e Bebidas ou Hemodialise do setor correto)
        pedidos_filtrados = db(
            (~db.solicitacao_refeicao.status.belongs(['Finalizado', 'Pago'])) &
            (db.auth_user.user_type.belongs(tipos_filtrados_ids)) &
            (
                (db.solicitacao_refeicao.data_solicitacao < hoje.date) |
                (
                    (db.horario_refeicoes.servido_inicio <= hoje.time()) &
                    (db.solicitacao_refeicao.data_solicitacao == hoje.date())
                )
            ) &
            (
                (db.cardapio.tipo.belongs(['A La Carte', 'Livre', 'Bebidas'])) |
                ((db.auth_user.user_type == db(db.user_type.name == 'Hemodialise').select(db.user_type.id).first().id) &
                 (db.auth_user.setor_id == setor_colaborador_hemodialise_id))
            )
        ).select(
            db.solicitacao_refeicao.ALL,
            db.cardapio.foto_do_prato,
            db.cardapio.nome,
            db.auth_user.first_name,
            db.auth_user.room,
            db.auth_user.observations,
            db.auth_user.user_type,
            db.setor.name,
            left=[
                db.cardapio.on(db.solicitacao_refeicao.prato_id == db.cardapio.id),
                db.horario_refeicoes.on(db.cardapio.tipo == db.horario_refeicoes.refeicao),
                db.auth_user.on(db.solicitacao_refeicao.solicitante_id == db.auth_user.id),
                db.setor.on(db.auth_user.setor_id == db.setor.id)
            ]
        )

        # Combinar todas as listas de pedidos
        todos_pedidos = pedidos_livres | pedidos_normais | pedidos_filtrados

        # Acessar `user_type.name` para cada pedido e definir uma prioridade
        for pedido in todos_pedidos:
            user_type_name = pedido.auth_user.user_type.name if pedido.auth_user.user_type else None
            pedido.user_type_name = user_type_name

        # Definir a prioridade de tipos de usuário para ordenação
        prioridade_tipos = {
            'Paciente': 1,
            'Paciente Convenio': 2,
            'Acompanhante': 3
        }

        # Ordenar a lista de pedidos
        pedidos_ordenados = sorted(
            todos_pedidos,
            key=lambda p: (
                prioridade_tipos.get(p.user_type_name, 5),  # Tipos prioritários têm valores menores
                p.solicitacao_refeicao.data_solicitacao  # Ordena por data de solicitação como fallback
            )
        )

        # Formatar os pedidos para JSON
        pedidos_json = [
            {
                'id': pedido.solicitacao_refeicao.id,
                'solicitante': pedido.auth_user.first_name,
                'setor': pedido.setor.name or '-',
                'prato': pedido.cardapio.nome,
                'foto': f"data:image/png;base64,{pedido.cardapio.foto_do_prato}" if pedido.cardapio.foto_do_prato else '',
                'quantidade': pedido.solicitacao_refeicao.quantidade_solicitada,
                'quarto': pedido.auth_user.room or '',
                'observacoes': pedido.auth_user.observations or '',
                'status': pedido.solicitacao_refeicao.status
            }
            for pedido in pedidos_ordenados
        ]

        return response.json({'status': 'success', 'pedidos': pedidos_json})

    except Exception as e:
        import traceback
        error_message = f"Erro ao processar a API: {str(e)}\n{traceback.format_exc()}"
        print(error_message)  # Log para depuração
        return response.json({'status': 'error', 'message': error_message})


@auth.requires_login()
def cancelar_pedido():
    try:
        pedido_id = request.post_vars.get('pedido_id')
        if not pedido_id:
            raise ValueError("ID do pedido não fornecido.")

        pedido = db(db.solicitacao_refeicao.id == pedido_id).select().first()
        if not pedido:
            raise ValueError("Pedido não encontrado.")

        # Recupera o valor do pedido e o solicitante real antes de deletar
        preco_pedido = pedido.preco or 0
        solicitante_real = pedido.solicitante_id

        # Remove o pedido
        db(db.solicitacao_refeicao.id == pedido_id).delete()

        # Atualiza o saldo do usuário
        saldo_atual = db(db.user_balance.user_id == solicitante_real).select().first()
        if saldo_atual:
            novo_saldo = max(0, saldo_atual.saldo_devedor - preco_pedido)
            saldo_atual.update_record(saldo_devedor=novo_saldo)

        db.commit()
        return response.json({'status': 'success', 'message': 'Pedido cancelado com sucesso!'})

    except Exception as e:
        db.rollback()
        return response.json({'status': 'error', 'message': str(e)})


@auth.requires(lambda: any(auth.has_membership(role) for role in ['Cozinha', 'Gestor', 'Colaborador', 'Administrador']))
def atualizar_status():
    try:
        pedido_id = request.post_vars['pedido_id']
        pedido = db.solicitacao_refeicao(pedido_id)

        if not pedido:
            return response.json({'status': 'failed', 'message': 'Pedido não encontrado'})

        novo_status = 'Em Preparação' if pedido.status == 'Pendente' else 'Finalizado'
        pedido.update_record(status=novo_status)
        db.commit()

        return response.json({'status': 'success', 'novo_status': novo_status})
    except Exception as e:
        return response.json({'status': 'failed', 'message': str(e)})


@auth.requires(lambda: any(auth.has_membership(role) for role in ['Cozinha', 'Gestor', 'Colaborador', 'Administrador']))
def finalizar_status():
    try:
        # Filtra para excluir IDs vazios ou inválidos
        pedidos_ids = [int(id) for id in request.post_vars['pedido_id'].split(',') if id.isdigit()]
        print("IDs recebidos para atualização:", pedidos_ids)  # Verificar se os IDs estão corretos

        if not pedidos_ids:
            return response.json({'status': 'failed', 'message': 'Nenhum pedido válido encontrado'})

        # Processa cada pedido
        for pedido_id in pedidos_ids:
            pedido = db.solicitacao_refeicao(pedido_id)
            if not pedido:
                print(f"Pedido {pedido_id} não encontrado")
                continue
            if pedido.status != 'Pendente':
                print(f"Status do pedido {pedido_id} não permite finalização")
                continue

            # Atualiza o status para cada pedido
            pedido.update_record(status='Finalizado')
            print(f"Pedido {pedido_id} atualizado para 'Finalizado'")

        db.commit()
        return response.json({'status': 'success', 'message': 'Pedidos finalizados com sucesso'})

    except Exception as e:
        print("Erro ao atualizar pedidos:", e)
        return response.json({'status': 'failed', 'message': str(e)})
