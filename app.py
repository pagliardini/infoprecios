from flask import Flask, render_template, request, redirect, url_for
from bs4 import BeautifulSoup
import requests
import pymssql
import json
import locale

app = Flask(__name__)

# Configurar locale para formatear moneda
locale.setlocale(locale.LC_ALL, 'es_AR.UTF-8')

# Cargar configuración de la base de datos desde config.json
with open('config.json') as config_file:
    config = json.load(config_file)

user = config['user']
password = config['password']
database = config['database']

# Cargar servidores desde servers.json
try:
    with open('servers.json') as servers_file:
        servers = json.load(servers_file)
except FileNotFoundError:
    servers = []

@app.route('/', methods=['GET', 'POST'])
def index():
    resultados = []
    imagen_producto = ""
    descripcion_producto = ""
    precio_referencia = ""
    if request.method == 'POST':
        ean = request.form.get('ean')
        if ean:
            # Obtener información de Pricely
            nombre_pricely, precio_pricely, imagen_producto, descripcion_producto = get_product_info(ean)
            if nombre_pricely and precio_pricely:
                resultados.append({
                    "CodigoEan": ean,
                    "Nombre": nombre_pricely,
                    "Precio": precio_pricely,
                    "Servidor": "Pricely"
                })
                # Imprimir el valor del precio antes de la conversión
                print(f"Precio de Pricely antes de la conversión: {precio_pricely}")
        # Eliminar símbolos y ajustar formato
            try:
                # Paso 1: Limpia el precio (quita símbolos y espacios)
                precio_pricely = precio_pricely.strip().replace('$', '').replace('.', '').replace(',', '.')

                # Paso 2: Convierte el precio a número flotante
                precio_pricely_num = float(precio_pricely)

                # Paso 3: Calcula el precio de referencia (+10%)
                precio_referencia_num = precio_pricely_num * 1.10

                # Paso 4: Redondea el precio de referencia al múltiplo superior de 50
                precio_referencia_num = ((precio_referencia_num + 49) // 50) * 50

                # Paso 5: Formatea el precio de referencia
                precio_referencia = locale.currency(precio_referencia_num, grouping=True)
            except ValueError as e:
                print(f"Error al convertir el precio: {e}")
                precio_referencia = "Error en el cálculo"
            
            
            # Obtener información de SQL Server
            for server in servers:
                resultados_sql = get_product_info_sql(server['ip'], ean, server['alias'])
                resultados.extend(resultados_sql)
    
    return render_template('index.html', resultados=resultados, imagen_producto=imagen_producto, descripcion_producto=descripcion_producto, precio_referencia=precio_referencia)

@app.route('/config', methods=['GET', 'POST'])
def config():
    if request.method == 'POST':
        action = request.form.get('action')
        alias = request.form.get('alias')
        ip = request.form.get('ip')
        if action == 'add' and alias and ip:
            # Verificar si el servidor ya existe
            for server in servers:
                if server['alias'] == alias:
                    server['ip'] = ip
                    break
            else:
                servers.append({'alias': alias, 'ip': ip})
        elif action == 'remove' and alias:
            servers[:] = [server for server in servers if server['alias'] != alias]
        elif action == 'bulk_remove':
            selected_servers = request.form.getlist('selected_servers')
            for alias in selected_servers:
                servers[:] = [server for server in servers if server['alias'] != alias]
        
        # Guardar cambios en servers.json
        with open('servers.json', 'w') as servers_file:
            json.dump(servers, servers_file)
        
        return redirect(url_for('config'))
    
    return render_template('config.html', servers=servers, check_server_status=check_server_status)

@app.route('/config/edit/<alias>', methods=['GET', 'POST'])
def edit_server(alias):
    if request.method == 'POST':
        ip = request.form.get('ip')
        for server in servers:
            if server['alias'] == alias:
                server['ip'] = ip
        
        # Guardar cambios en servers.json
        with open('servers.json', 'w') as servers_file:
            json.dump(servers, servers_file)
        
        return redirect(url_for('config'))
    else:
        server_to_edit = next((server for server in servers if server['alias'] == alias), None)
        return render_template('config.html', servers=servers, server_to_edit=server_to_edit, check_server_status=check_server_status)

@app.route('/config/remove/<alias>', methods=['POST'])
def remove_server(alias):
    servers[:] = [server for server in servers if server['alias'] != alias]
    
    # Guardar cambios en servers.json
    with open('servers.json', 'w') as servers_file:
        json.dump(servers, servers_file)
    
    return redirect(url_for('config'))

def check_server_status(ip):
    if ip is None:
        return False
    try:
        conn = pymssql.connect(ip, user, password, database, timeout=1)
        conn.close()
        return True
    except pymssql.Error:
        return False

def get_product_info(ean):
    try:
        url = f"https://pricely.ar/product/{ean}"
        response = requests.get(url)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        nombre_producto = soup.select_one(
            "body > main > div > div.max-w-5xl.w-full.bg-white.p-8.md\\:p-4.shadow-xl.mb-8 > div.flex.items-center.md\\:flex-row.gap-4.w-full.flex-col.md\\:p-4 > div.flex.flex-col.justify-center > h1"
        )
        nombre_producto = nombre_producto.text.strip() if nombre_producto else "Nombre no encontrado"

        precio_promedio = soup.select_one(
            "body > main > div > div.max-w-5xl.w-full.bg-white.p-8.md\\:p-4.shadow-xl.mb-8 > div.md\\:p-4.mt-4 > div > div > div.flex.flex-col.md\\:flex-row.items-center.justify-between.gap-4.mt-8 > div > h3"
        )
        precio_promedio = precio_promedio.text.strip() if precio_promedio else "Precio no encontrado"

        imagen_producto = soup.select_one(
            "body > main > div > div.max-w-5xl.w-full.bg-white.p-8.md\:p-4.shadow-xl.mb-8 > div.flex.items-center.md\:flex-row.gap-4.w-full.flex-col.md\:p-4 > div:nth-child(1) > a > div > img"
        )
        imagen_producto = imagen_producto['src'] if imagen_producto else ""

        descripcion_producto = soup.select_one(
            "body > main > div > div.max-w-5xl.w-full.bg-white.p-8.md\:p-4.shadow-xl.mb-8 > div.flex.items-center.md\:flex-row.gap-4.w-full.flex-col.md\:p-4 > div.flex.flex-col.justify-center > div.mb-1.text-zinc-600.text-xs.mt-2"
        )
        descripcion_producto = descripcion_producto.text.strip() if descripcion_producto else "Descripción no encontrada"

        return nombre_producto, precio_promedio, imagen_producto, descripcion_producto

    except requests.exceptions.RequestException as e:
        return "Error al conectarse con Pricely", str(e), "", ""
    except AttributeError:
        return "No se pudo extraer información del producto.", "", "", ""

def get_product_info_sql(server_ip, ean, alias):
    query = f"""
    SELECT Descripcion, Precio_Venta
    FROM Productos
    WHERE Id_Producto = '{ean}' OR Id_Producto1 = '{ean}' OR Id_Producto2 = '{ean}' OR Id_Producto3 = '{ean}'
    """
    
    resultados = []
    try:
        conn = pymssql.connect(server_ip, user, password, database, timeout=0.2)
        cursor = conn.cursor(as_dict=True)
        cursor.execute(query)
        for row in cursor:
            resultados.append({
                "CodigoEan": ean,
                "Nombre": row['Descripcion'],
                "Precio": locale.currency(row['Precio_Venta'], grouping=True),
                "Servidor": alias
            })
        conn.close()
    except pymssql.Error as e:
        print(f"Error al conectarse a SQL Server en {alias}: {e}")
    
    return resultados

if __name__ == '__main__':
    app.run(port=5000, debug=True)