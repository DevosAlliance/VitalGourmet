# Sistema de Gestão de Refeições Hospitalares

## 📋 Visão Geral

Este sistema gerencia pedidos de refeições em ambiente hospitalar, controlando gratuidades, horários e financeiro de forma otimizada para diferentes tipos de usuários.

## 👥 Tipos de Usuário e Setores

### Tipos de Usuário (`user_type`)

- **Administrador**
- **Colaborador**
- **Gestor**
- **Paciente**
- **Instrumentador**
- **Paciente Convenio**
- **Acompanhante**
- **Hemodialise**
- **Medico**

### Setores (`setor`)

Os setores funcionam como uma localização mais específica do usuário dentro do hospital:

- Administrador
- Administrativo
- Medico
- Recepção
- Enfermagem
- Hemodialise
- Nutrição
- Cozinha
- Faturamento
- Radiologia
- Serviços Gerais
- Paciente
- Paciente Convenio
- Acompanhante

## 🆓 Regras de Gratuidade

### Gratuidade Ilimitada

Usuários com **gratuidade total** em todos os pratos:

- `Colaborador`
- `Medico`
- `Instrumentador`
- `Hemodialise`

### Gratuidade Limitada

#### Paciente Regular

- ✅ Gratuidade no **primeiro prato de cada tipo**
- ❌ Acompanhantes **NÃO herdam** gratuidade

#### Paciente Convênio

- ✅ Gratuidade no **primeiro prato de cada tipo**
- ✅ Acompanhantes **HERDAM** gratuidade
- ⚠️ **Condição**: Paciente deve atender requisitos de idade mínima/máxima

### Particularidades por Setor

| Setor                       | Múltiplos Pratos no Mesmo Pedido |
| --------------------------- | -------------------------------- |
| **Hemodialise**             | ✅ Permitido                     |
| **Colaborador Hemodiálise** | ❌ Não permitido                 |

### Exceções às Regras de Gratuidade

Os seguintes tipos de pedido **não seguem** regras de gratuidade:

- A la carte
- Livre
- Bebidas

> **Nota**: Essas exceções podem ser editadas nas configurações do sistema.

## 💰 Sistema Financeiro

### Estrutura de Preços

Cada solicitação possui um valor registrado:

```sql
db.define_table('solicitacao_refeicao',
   ...
    Field('preco', 'decimal(10, 2)', required=True, label="Preço"),
   ...
)
```

### Saldo Devedor

O sistema mantém um saldo consolidado por usuário para otimização:

```sql
db.define_table('user_balance',
    Field('user_id', 'reference auth_user', unique=True),
    Field('saldo_devedor', 'decimal(10,2)', default=0),
    ...
)
```

**Motivo da Implementação**: Esta abordagem evita cálculos em tempo real sobre todos os pedidos, que anteriormente causavam:

- ⏱️ Demoras de 5+ minutos nas APIs
- 🔮 Potencial de 30+ minutos com grande volume de dados
- ⚠️ Risco de sobrecarga e erros do sistema

## 🔌 APIs do Cardápio

### `api_listar_pratos_para_usuario`

**Função**: Lista pratos disponíveis para o usuário logado

- Verifica direitos de gratuidade baseado no `user_id`
- Valida disponibilidade por horário
- Filtra pratos permitidos para o tipo de usuário

### `api_registrar_solicitacao_refeicao`

**Função**: Processa solicitação de refeição

- Executa as **mesmas validações** da API de listagem
- Garante consistência entre visualização e pedido
- Registra a solicitação após validação completa

## ⏰ Horários de Refeições

### Estrutura da Tabela

```sql
db.define_table('horario_refeicoes',
    Field('tipo_usuario', 'json', required=True, label="Tipos de Usuário"),
    Field('refeicao', 'string', required=True),
    Field('pedido_inicio', 'time', required=True),  # Início do período de pedidos
    Field('pedido_fim', 'time', required=True),     # Fim do período de pedidos
    Field('servido_inicio', 'time', required=True), # Início do serviço pela cozinha
    auth.signature,
    format='%(refeicao)s',
)
```

### Fluxo de Horários

1. **Pedido**: Usuário pode solicitar entre `pedido_inicio` e `pedido_fim`
2. **Preparo**: Cozinha inicia preparo a partir de `servido_inicio`
3. **Entrega**: Baseado no horário de serviço configurado

## 🍽️ Cardápio

### Estrutura da Tabela

```sql
db.define_table('cardapio',
    Field('nome', 'string', required=True, label="Nome do Prato"),
    Field('descricao', 'text', required=True, label="Descrição"),
    Field('tipo', 'string', requires=IS_IN_DB(db, 'horario_refeicoes.refeicao', '%(refeicao)s'), label="Tipo de Refeição"),
    Field('ingredientes', 'json', required=True, label="Ingredientes"),
    Field('tipos_usuario', 'json', required=True, label="Tipos de Usuário"),
    Field('dias_semana', 'json', requires=IS_IN_SET(['Segunda-feira', 'Terca-feira', 'Quarta-feira', 'Quinta-feira', 'Sexta-feira', 'Sabado', 'Domingo'], multiple=True), required=True, label="Dias da Semana"),
    Field('foto_do_prato', 'text', label="Foto do Prato"),
    Field('preco', 'decimal(10, 2)', required=True, label="Preço"),
    format='%(nome)s',
)
```

### Campos Principais

| Campo           | Tipo    | Descrição                                       |
| --------------- | ------- | ----------------------------------------------- |
| `nome`          | String  | Nome do prato                                   |
| `descricao`     | Text    | Descrição detalhada                             |
| `tipo`          | String  | Tipo de refeição (lanche, almoço, jantar, etc.) |
| `ingredientes`  | JSON    | Lista de ingredientes                           |
| `tipos_usuario` | JSON    | Tipos de usuário que podem solicitar            |
| `dias_semana`   | JSON    | Dias da semana disponíveis                      |
| `foto_do_prato` | Text    | URL/caminho da imagem                           |
| `preco`         | Decimal | Valor do prato                                  |

### Validações

- **Tipo de Refeição**: Deve existir na tabela `horario_refeicoes`
- **Dias da Semana**: Valores fixos de Segunda a Domingo
- **Tipos de Usuário**: JSON array com tipos válidos

## 🔄 Fluxo de Funcionamento

1. **Login do Usuário** → Sistema identifica `user_type` e `setor`
2. **Consulta Cardápio** → API valida horários e gratuidades
3. **Seleção de Prato** → Sistema verifica elegibilidade
4. **Confirmação de Pedido** → Validação final e registro
5. **Atualização Financeira** → Incremento no `saldo_devedor` se aplicável

## ⚙️ Configurações

- Exceções de gratuidade podem ser editadas
- Horários flexíveis por tipo de usuário
- Preços configuráveis por prato
- Dias de funcionamento personalizáveis

---

**Desenvolvido para**: Ambiente hospitalar com múltiplos perfis de usuário  
**Foco**: Performance, controle financeiro e regras de negócio específicas
