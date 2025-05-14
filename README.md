Instalação do web2py no Ubuntu (Amazon Lightsail)
Este tutorial orienta você na instalação do web2py em uma instância Ubuntu no Amazon Lightsail.

Passos

1. Acessar sua instância Lightsail
   Conecte-se à sua instância Ubuntu no Amazon Lightsail via SSH:

2. Atualizar o sistema
   Antes de começar, é importante garantir que todos os pacotes do sistema estejam atualizados:

```bash
sudo apt-get update
sudo apt-get upgrade -y
```

3. Instalar dependências
   Instale o Python, unzip e outros pacotes necessários:

```bash
sudo apt-get install python3 python3-pip build-essential unzip -y
```

4. Baixar e configurar o web2py
   Baixe o web2py usando o wget com a opção --no-check-certificate para ignorar a verificação de certificado SSL:

```bash
wget --no-check-certificate https://web2py.com/examples/static/web2py_src.zip
```

```bash
unzip web2py_src.zip
cd web2py
```

6. Configurar e executar o script de instalação
   Dê permissão de execução ao script de instalação do web2py:

```bash
chmod +x scripts/setup-web2py-ubuntu.sh
```

Execute o script para configurar o web2py no seu servidor:

```bash
sudo ./scripts/setup-web2py-ubuntu.sh
```

7. Acessar o web2py
   Após a instalação, você pode acessar o web2py através do navegador:

```bash
http://<seu-endereco-ip>:8000
```

8. Configurações adicionais
   Defina uma senha de administrador: Quando você acessar o web2py pela primeira vez, será solicitado que você defina uma senha de administrador.
   Configurar SSL: Considere configurar SSL para maior segurança.
