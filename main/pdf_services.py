from fpdf import FPDF

# Ancho en mm de la columna DETALLE: el valor normal deja lugar a la columna
# de subtotales; el "solo" ocupa tambien ese espacio cuando no hay importes
ANCHO_DETALLE = 86
ANCHO_DETALLE_SOLO = 121.5

# Tope de caracteres del detalle para que no invada la columna siguiente ni el
# borde del comprobante, proporcional al ancho disponible en cada caso. Al subir
# el cuerpo de los items a 11 el renglon ocupa mas, asi que bajo los topes
CHARS_DETALLE = 39
CHARS_DETALLE_SOLO = 54


def _formato_importe(valor):
    # Formato argentino sin simbolo: punto para los miles y coma para los
    # decimales ("12.100,00"). Convierto el separador estándar de Python al
    # criterio local.
    try:
        s = f"{float(valor or 0):,.2f}"
    except (TypeError, ValueError):
        s = "0.00"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _formato_moneda(valor):
    # Igual que _formato_importe pero con el signo pesos adelante ("$ 12.100,00")
    return f"$ {_formato_importe(valor)}"


def _latin1(texto):
    """Deja el texto en el juego de caracteres que admiten las fuentes base.

    Las fuentes core de FPDF (Arial/Helvetica) solo codifican latin-1: un guion
    largo o una comilla tipografica pegada desde Word haria fallar la generacion
    entera del PDF. Los reemplazo por '?' en vez de romper el comprobante.
    """
    return str(texto or "").encode("latin-1", errors="replace").decode("latin-1")


class Remito(FPDF):
    def __init__(self, id_operacion, fecha, nombre, localidad, direccion, productos, apellido=" ", cuit=" ", telefono="", observaciones="", total=0, mostrar_importes=True):
        # A4 Apaisado (Landscape): 297mm x 210mm
        super().__init__(orientation='L', format='A4')
        self.set_auto_page_break(auto=True, margin=5)
        self.id_operacion = id_operacion
        self.fecha = fecha
        self.nombre = nombre
        self.apellido = apellido
        self.localidad = localidad
        self.direccion = direccion
        self.productos = productos
        self.cuit = cuit
        self.telefono = telefono
        # Nota opcional de la operación; el campo se imprime siempre (con o
        # sin texto) para poder completarlo a mano, con tope de 250 caracteres
        self.observaciones = str(observaciones or "")[:250]
        # Total de la operación, para la casilla grande al pie del comprobante
        self.total = total
        # Los remitos que se emiten sin importes (usuarios no administrativos)
        # omiten la columna de subtotales y la casilla de total
        self.mostrar_importes = mostrar_importes

    def header(self):
        self.dibujar_esqueleto(0, "ORIGINAL")
        self.dibujar_esqueleto(148.5, "DUPLICADO")

    def dibujar_esqueleto(self, offset_x, etiqueta):
        # Esqueleto principal del comprobante
        self.set_line_width(0.3)
        self.rect(offset_x + 5, 5, 138.5, 200)

        # Etiqueta Superior Center
        self.set_font('Arial', 'B', 8)
        self.set_xy(offset_x + 5, 5)
        self.cell(138.5, 5, etiqueta, 0, 0, 'C')

        self.line(offset_x + 5, 45, offset_x + 143.5, 45) 

        id_str = str(self.id_operacion).zfill(5)

        # Casilla 'X'
        self.set_font('Arial', 'B', 24)
        self.rect(offset_x + 68, 12, 12, 12)
        self.set_xy(offset_x + 68, 12)
        self.cell(12, 12, 'X', 0, 0, 'C')

        # Texto debajo de 'X'
        self.set_font('Arial', 'B', 5)
        self.set_xy(offset_x + 60, 26)
        self.cell(28, 3, 'DOCUMENTO', 0, 2, 'C')
        self.cell(28, 3, 'NO VALIDO COMO', 0, 2, 'C')
        self.cell(28, 3, 'FACTURA', 0, 2, 'C')

        self.line(offset_x + 74, 38, offset_x + 74, 45)

        # Textos de la derecha
        self.set_font('Arial', 'B', 18)
        self.set_xy(offset_x + 80, 12)
        self.cell(63.5, 10, 'REMITO', 0, 1, 'C')

        self.set_font('Arial', '', 14)
        self.set_xy(offset_x + 80, 22)
        self.cell(63.5, 8, f'Nº {id_str}', 0, 1, 'C')

        self.set_font('Arial', '', 9)
        self.set_xy(offset_x + 80, 30)
        self.cell(63.5, 5, 'FECHA', 0, 1, 'C')

        # Fecha
        self.rect(offset_x + 90, 36, 12, 6)
        self.rect(offset_x + 104, 36, 12, 6)
        self.rect(offset_x + 118, 36, 16, 6)

        d, m, y = "", "", ""
        if hasattr(self.fecha, "strftime"):
            d, m, y = self.fecha.strftime("%d"), self.fecha.strftime("%m"), self.fecha.strftime("%Y")
        elif isinstance(self.fecha, str):
            parts = []
            if '-' in self.fecha:
                parts = self.fecha.split('-')
            elif '/' in self.fecha:
                parts = self.fecha.split('/')

            if len(parts) == 3:
                if len(parts[0]) == 4:
                    d, m, y = parts[2], parts[1], parts[0]
                else:
                    d, m, y = parts[0], parts[1], parts[2]
            else:
                d = self.fecha

        if len(y) == 2: y = "20" + y

        self.set_text_color(0, 0, 0)  # Los datos van en negro
        self.set_font('Arial', '', 11)  # La fecha cargada, +2 sobre la etiqueta
        self.set_xy(offset_x + 90, 36)
        self.cell(12, 6, str(d)[:2], 0, 0, 'C')
        self.set_xy(offset_x + 104, 36)
        self.cell(12, 6, str(m)[:2], 0, 0, 'C')
        self.set_xy(offset_x + 118, 36)
        self.cell(16, 6, str(y)[:4], 0, 0, 'C')
        self.set_text_color(0, 0, 0)

        # Datos del Cliente. La etiqueta va en su cuerpo base y el dato +2, ambos
        # en negro para que el contenido cargado se lea lo mas fuerte posible
        LABEL_SIZE = 9
        DATO_SIZE = 11
        self.set_text_color(0, 0, 0)

        # Señor/a
        self.set_xy(offset_x + 5, 47)
        self.set_font('Arial', '', LABEL_SIZE)
        self.cell(self.get_string_width(' Señor/a: '), 6, ' Señor/a: ')
        self.set_font('Arial', '', DATO_SIZE)
        self.cell(0, 6, f'{self.nombre} {self.apellido}')
        self.line(offset_x + 5, 54, offset_x + 143.5, 54)

        # Fila 2: CUIT y Teléfono (intercambiada con Domicilio)
        # CUIT a la izquierda
        self.set_xy(offset_x + 5, 55)
        self.set_font('Arial', '', LABEL_SIZE)
        label_cuit = " CUIT: "
        self.cell(self.get_string_width(label_cuit), 6, label_cuit)
        self.set_font('Arial', '', DATO_SIZE)
        self.cell(0, 6, f'{self.cuit if self.cuit else ""}')

        # Teléfono desde la mitad (138.5 / 2 = 69.25)
        self.set_xy(offset_x + 5 + 69.25, 55)
        self.set_font('Arial', '', LABEL_SIZE)
        label_tel = " Teléfono: "
        self.cell(self.get_string_width(label_tel), 6, label_tel)
        self.set_font('Arial', '', DATO_SIZE)
        self.cell(0, 6, f'{self.telefono if self.telefono else ""}')

        self.line(offset_x + 5, 62, offset_x + 143.5, 62)

        # Fila 3: Domicilio
        self.set_xy(offset_x + 5, 63)
        self.set_font('Arial', '', LABEL_SIZE)
        self.cell(self.get_string_width(' Domicilio: '), 6, ' Domicilio: ')
        self.set_font('Arial', '', DATO_SIZE)
        dir_str = self.direccion if self.direccion else ""
        loc_str = self.localidad if self.localidad else ""
        domicilio_val = f'{dir_str}' + (f' - {loc_str}' if loc_str else '')
        self.cell(0, 6, domicilio_val)
        self.line(offset_x + 5, 70, offset_x + 143.5, 70)

        # Reset color para encabezados de tabla
        self.set_text_color(0, 0, 0)

        # Fila 4: Observaciones (debajo del domicilio). La etiqueta se imprime
        # siempre; el texto acompaña el cuerpo de los datos y se parte en 3 lineas
        self.set_font('Arial', 'B', LABEL_SIZE)
        self.set_xy(offset_x + 5, 71)
        self.set_text_color(0, 0, 0)
        self.cell(self.get_string_width(' Observaciones: '), 4, ' Observaciones: ')

        self.set_font('Arial', '', 10)
        self.set_text_color(0, 0, 0)
        y_obs = 75.5
        for texto_linea in self._lineas_observaciones(133):
            self.set_xy(offset_x + 6, y_obs)
            self.cell(133, 2.8, texto_linea, 0, 0, 'L')
            y_obs += 2.8
        self.set_text_color(0, 0, 0)
        self.line(offset_x + 5, 84, offset_x + 143.5, 84)

        # Columnas: CANT. | DETALLE | SUBTOTAL. Sin importes queda CANT. |
        # DETALLE, y el detalle se estira hasta el borde del comprobante
        self.set_font('Arial', 'B', 9)
        self.set_xy(offset_x + 5, 84)
        self.cell(17, 8, 'CANT.', 0, 0, 'C')
        self.set_xy(offset_x + 22, 84)
        self.cell(ANCHO_DETALLE if self.mostrar_importes else ANCHO_DETALLE_SOLO, 8, 'DETALLE', 0, 0, 'C')
        if self.mostrar_importes:
            self.set_xy(offset_x + 108, 84)
            self.cell(35.5, 8, 'SUBTOTAL', 0, 0, 'C')
        self.line(offset_x + 5, 92, offset_x + 143.5, 92)

        # Lineas verticales de la tabla (cortan en 193; las casillas de firma y
        # total las tapan con relleno blanco sobre la ultima pagina)
        self.line(offset_x + 22, 84, offset_x + 22, 193)
        if self.mostrar_importes:
            self.line(offset_x + 108, 84, offset_x + 108, 193)

    def draw_products(self):
        y_pos = 92
        for prod in self.productos:
            # Corto antes de dibujar para dejar libre el pie (firma + total)
            if y_pos + 8 > 192:
                self.add_page()
                y_pos = 92

            self.set_font('Arial', '', 11)
            self.set_text_color(0, 0, 0) # Datos de productos en negro, +2

            cant = str(prod.get('cantidad', '')) if isinstance(prod, dict) else str(getattr(prod, 'cantidad', ''))

            if isinstance(prod, dict):
                detalle = str(prod.get('detalle', prod.get('nombre', prod.get('producto', '-'))))
                subtotal = prod.get('subtotal', 0)
            else:
                if hasattr(prod, 'producto'):
                    detalle = getattr(prod.producto, 'nombre', str(prod.producto))
                else:
                    detalle = str(getattr(prod, 'detalle', getattr(prod, 'nombre', '-')))
                subtotal = getattr(prod, 'subtotal', 0)

            sub_str = _formato_moneda(subtotal) if self.mostrar_importes else ''
            self.escribir_fila(0, y_pos, cant, detalle, sub_str)
            self.escribir_fila(148.5, y_pos, cant, detalle, sub_str)

            y_pos += 8
            self.set_text_color(0, 0, 0) # Líneas en negro
            self.line(5, y_pos, 143.5, y_pos)
            self.line(148.5 + 5, y_pos, 148.5 + 143.5, y_pos)

        self.dibujar_firma(0)
        self.dibujar_firma(148.5)
        if self.mostrar_importes:
            self.dibujar_total(0)
            self.dibujar_total(148.5)

    def escribir_fila(self, offset_x, y, c, d, s):
        self.set_xy(offset_x + 5, y)
        self.cell(17, 8, c, 0, 0, 'C')
        self.set_xy(offset_x + 22, y)
        # Detalle con limite de caracteres para no invadir la columna de subtotal
        if self.mostrar_importes:
            self.cell(ANCHO_DETALLE, 8, f' {d[:CHARS_DETALLE]}', 0, 0, 'L')
            self.set_xy(offset_x + 108, y)
            self.cell(34.5, 8, s, 0, 0, 'R')
        else:
            self.cell(ANCHO_DETALLE_SOLO, 8, f' {d[:CHARS_DETALLE_SOLO]}', 0, 0, 'L')

    def dibujar_total(self, offset_x):
        """
        Casilla de total al pie derecho del comprobante, en la posicion que
        antes ocupaba la firma. La etiqueta "TOTAL" va arriba del importe.
        """
        self.set_auto_page_break(auto=False)

        # Relleno blanco para tapar las lineas de la grilla dentro de la casilla
        self.set_fill_color(255, 255, 255)
        self.set_draw_color(0, 0, 0)
        self.rect(offset_x + 103.5, 193, 40, 12, 'DF')

        self.set_text_color(0, 0, 0)
        self.set_font('Arial', 'B', 8)
        self.set_xy(offset_x + 103.5, 194)
        self.cell(40, 4, 'TOTAL', 0, 0, 'C')

        self.set_font('Arial', 'B', 13)
        self.set_xy(offset_x + 103.5, 198)
        self.cell(40, 5, _formato_moneda(self.total), 0, 0, 'C')

    def _lineas_observaciones(self, ancho_max):
        """
        Parte la observación en hasta 3 líneas que entren en 'ancho_max' mm con
        la fuente actual; si no entra, la última corta con elipsis. Debe
        llamarse con la fuente ya seteada (usa get_string_width). Sin nota
        devuelve una lista vacía.
        """
        if not self.observaciones:
            return []

        lineas = []
        linea = ''
        for palabra in self.observaciones.split():
            candidata = f'{linea} {palabra}'.strip()
            if self.get_string_width(candidata) <= ancho_max:
                linea = candidata
            else:
                if linea:
                    lineas.append(linea)
                # Palabra mas larga que el ancho: se corta por caracteres
                while self.get_string_width(palabra) > ancho_max:
                    corte = len(palabra)
                    while corte > 1 and self.get_string_width(palabra[:corte]) > ancho_max:
                        corte -= 1
                    lineas.append(palabra[:corte])
                    palabra = palabra[corte:]
                linea = palabra
        if linea:
            lineas.append(linea)

        if len(lineas) > 3:
            lineas = lineas[:3]
            lineas[-1] = lineas[-1][:-1] + '…'
        return lineas

    def dibujar_firma(self, offset_x):
        self.set_auto_page_break(auto=False)
        self.set_fill_color(255, 255, 255)
        self.set_draw_color(0, 0, 0)
        # Recuadro de firma al pie izquierdo del comprobante
        self.rect(offset_x + 5, 193, 40, 12, "DF")

        self.set_font("Arial", "B", 7)
        self.set_text_color(0, 0, 0)

        # Etiqueta 'FIRMA' arriba del recuadro
        self.set_xy(offset_x + 5, 193.5)
        self.cell(40, 4, "FIRMA", 0, 0, "C")

    def generate_pdf(self, path=None):
        self.add_page()
        self.draw_products()
        return _salida_pdf(self, path)


def _salida_pdf(documento, path=None):
    """Devuelve el PDF ya armado como bytes, o lo escribe en disco si hay ruta.

    Contempla las dos firmas de output(): la moderna de fpdf2 (devuelve bytearray)
    y la vieja con dest='S'.
    """
    if path:
        return documento.output(path)
    try:
        salida = documento.output()
        return bytes(salida) if isinstance(salida, bytearray) else salida
    except TypeError:
        return documento.output(dest='S').encode('latin1')


# ==========================================================================
#  RESUMEN DE CUENTA CORRIENTE (libro Debe / Haber)
# ==========================================================================

# Grilla del resumen sobre A4 vertical (210 x 297 mm): margenes de 12 mm dejan
# 186 mm utiles, repartidos entre las cinco columnas del libro.
#
# No hay columna DETALLE: el detalle de cada movimiento (sus productos, o la
# leyenda del pago o del flete) va debajo del comprobante y no al lado. Asi el
# ancho que ocupaba se reparte entre Debe, Haber y Saldo, que son las que se
# desbordaban cuando los importes tienen muchos digitos.
MARGEN = 12
X_FECHA = MARGEN            # 25 mm, entra la fecha con el guion que la une al comprobante
X_COMPROBANTE = 37          # 71 mm, la mas ancha: adentro entran los productos
X_DEBE = 108                # 30 mm
X_HABER = 138               # 30 mm
X_SALDO = 168               # 30 mm
X_FIN = 198
ANCHO_IMPORTE = 30
# Donde arranca la segunda columna del bloque de datos del cliente (CUIT/telefono)
X_DATOS_DERECHA = 120

# Ancho reservado al subtotal de cada producto: va dentro de la columna del
# comprobante y no en Debe/Haber, que quedan para el importe de la operacion y
# no se ensucian con los parciales. Los productos no llevan sangria: arrancan
# en la misma vertical que el "Venta Nro ..." que los agrupa.
ANCHO_SUBTOTAL_ITEM = 22

# Alturas: donde arranca la grilla, donde cortan las filas para dejar sitio al
# recuadro de totales, y cuanto mide cada renglon. Y_GRILLA es el piso: cuando
# el resumen abre con el saldo anterior la grilla baja ese renglon (ver
# self.y_grilla), porque el arrastre va afuera de la tabla y necesita su lugar
Y_GRILLA = 40
ALTO_CABECERA_TABLA = 8
ALTO_SALDO_ANTERIOR = 7
Y_LIMITE_FILAS = 262
ALTO_FILA = 7
ALTO_ITEM = 4.5

# Verde pino del isologo, en RGB, para el filete del membrete
PINO = (22, 52, 44)
GRIS_DATO = (80, 80, 80)
GRIS_LINEA = (190, 190, 190)

# Los saldos se pintan segun de que lado quedan: verde el positivo, rojo el
# negativo. Es lo primero que busca el cliente cuando abre el resumen
VERDE_SALDO = (21, 115, 71)
ROJO_SALDO = (176, 32, 32)


class ResumenCuenta(FPDF):
    """Resumen de cuenta corriente de un cliente en formato Debe / Haber / Saldo.

    Es el libro rayado clasico: una fila por movimiento, las columnas de importes
    encolumnadas entre filetes verticales y el saldo acumulandose renglon a
    renglon. Los movimientos ya vienen ordenados y con su saldo calculado desde
    services.obtener_movimientos_cuenta_corriente().
    """

    def __init__(self, cliente, movimientos, totales, desde=None, hasta=None,
                 saldo_anterior=None, fecha_emision=None):
        super().__init__(orientation='P', format='A4')
        # La paginacion la manejo a mano: cada fila chequea si entra antes de
        # dibujarse, asi el recuadro de totales nunca queda partido
        self.set_auto_page_break(auto=False)
        self.set_margins(MARGEN, MARGEN, MARGEN)
        self.cliente = cliente
        self.movimientos = movimientos
        self.totales = totales
        self.desde = desde
        self.hasta = hasta
        self.saldo_anterior = saldo_anterior
        self.fecha_emision = fecha_emision

        self.y_grilla = Y_GRILLA
        self.y_cabecera = Y_GRILLA + ALTO_CABECERA_TABLA
        self.alias_nb_pages()

    # ---------------------------------------------------------------- membrete
    def header(self):
        self._resolver_alturas()
        self._dibujar_membrete()
        self._dibujar_datos_cliente()
        self._dibujar_saldo_anterior()
        self._dibujar_grilla()

    def _resolver_alturas(self):
        """Fija donde arranca la grilla en la pagina que se esta dibujando.

        El renglon del saldo anterior va entre los datos del cliente y la tabla,
        asi que en la primera hoja empuja la grilla hacia abajo. En las que
        siguen no se repite y la tabla vuelve a su altura de siempre, para no
        dejar una franja en blanco arrastrada por todo el resumen.
        """
        self.y_grilla = Y_GRILLA + (ALTO_SALDO_ANTERIOR if self._muestra_saldo_anterior() else 0)
        self.y_cabecera = self.y_grilla + ALTO_CABECERA_TABLA

    def _muestra_saldo_anterior(self):
        return self.saldo_anterior is not None and self.page_no() == 1

    def _dibujar_membrete(self):
        # Sin datos del emisor: a la izquierda que documento es, a la derecha a
        # que periodo corresponde y cuando se emitio
        self.set_text_color(*PINO)
        self.set_font('Arial', 'B', 14)
        self.set_xy(MARGEN, 13)
        self.cell(110, 7, 'RESUMEN DE CUENTA CORRIENTE', 0, 0, 'L')

        self.set_font('Arial', '', 8)
        self.set_text_color(*GRIS_DATO)
        self.set_xy(110, 13)
        self.cell(X_FIN - 110, 4, f'Período: {self._texto_periodo()}', 0, 0, 'R')
        self.set_xy(110, 17.5)
        self.cell(X_FIN - 110, 4, f'Emitido el {self._fecha_corta(self.fecha_emision)}', 0, 0, 'R')

        # Filete de marca que separa el membrete de los datos del cliente
        self.set_draw_color(*PINO)
        self.set_line_width(0.6)
        self.line(MARGEN, 24, X_FIN, 24)

    def _dibujar_datos_cliente(self):
        nombre = f"{self.cliente.nombre} {self.cliente.apellido or ''}".strip()
        cuit = self.cliente.cuit or "-"
        domicilio = " - ".join(p for p in [self.cliente.direccion, self.cliente.localidad] if p) or "-"
        telefono = self.cliente.telefono or "-"

        # Dos columnas de datos: la del cliente a la izquierda (hasta donde arranca
        # la fiscal) y la fiscal a la derecha, contra el borde del comprobante
        ancho_izquierda = X_DATOS_DERECHA - MARGEN - 2
        ancho_derecha = X_FIN - X_DATOS_DERECHA
        self._par_etiqueta_dato(MARGEN, 27, 'Señor/a: ', nombre, ancho_izquierda, negrita_dato=True)
        self._par_etiqueta_dato(X_DATOS_DERECHA, 27, 'CUIT: ', cuit, ancho_derecha)
        self._par_etiqueta_dato(MARGEN, 32.5, 'Domicilio: ', domicilio, ancho_izquierda)
        self._par_etiqueta_dato(X_DATOS_DERECHA, 32.5, 'Teléfono: ', telefono, ancho_derecha)

        self.set_draw_color(0, 0, 0)
        self.set_line_width(0.2)
        self.line(MARGEN, 38, X_FIN, 38)

    def _par_etiqueta_dato(self, x, y, etiqueta, dato, ancho, negrita_dato=False):
        """Escribe 'Etiqueta: dato' con la etiqueta en negro y el dato en gris.

        El dato se recorta al espacio que sobra: un nombre o un domicilio largo
        se pisaria con la columna de al lado, que en A4 vertical arranca cerca.
        """
        self.set_xy(x, y)
        self.set_font('Arial', '', 8)
        self.set_text_color(0, 0, 0)
        ancho_etiqueta = self.get_string_width(etiqueta)
        self.cell(ancho_etiqueta, 4, etiqueta, 0, 0, 'L')

        # El dato va +2 sobre la etiqueta y en negro para que se lea mas fuerte
        self.set_font('Arial', 'B' if negrita_dato else '', 10.5 if negrita_dato else 10)
        self.set_text_color(0, 0, 0)
        self.cell(ancho - ancho_etiqueta, 4, self._recortar(dato, ancho - ancho_etiqueta), 0, 0, 'L')
        self.set_text_color(0, 0, 0)

    def _dibujar_saldo_anterior(self):
        """Renglon de arrastre: con que saldo llega el cliente al periodo.

        Va afuera de la grilla, arriba de todo, porque no es un movimiento del
        periodo sino el punto de partida del que arranca la columna SALDO. Se
        repite en cada pagina junto con el resto de la cabecera.
        """
        if not self._muestra_saldo_anterior():
            return

        y = Y_GRILLA + 1
        self.set_font('Arial', 'B', 8)
        self.set_text_color(0, 0, 0)
        self.set_xy(MARGEN, y)
        self.cell(90, 5, f'SALDO ANTERIOR AL {self._fecha_corta(self.desde)}', 0, 0, 'L')

        texto = _formato_importe(self.saldo_anterior)
        self._fuente_que_entra(texto, ANCHO_IMPORTE - 2, 'B', 11)
        self.set_text_color(*self._color_saldo(self.saldo_anterior))
        self.set_xy(X_SALDO, y)
        self.cell(ANCHO_IMPORTE - 2, 5, texto, 0, 0, 'R')
        self.set_text_color(0, 0, 0)

    @staticmethod
    def _color_saldo(valor):
        """Verde el saldo a favor, rojo el saldo en contra, negro el cero."""
        if valor > 0:
            return VERDE_SALDO
        if valor < 0:
            return ROJO_SALDO
        return (0, 0, 0)

    # ----------------------------------------------------------------- grilla
    def _dibujar_grilla(self):
        # Encabezados de las seis columnas
        self.set_font('Arial', 'B', 7.5)
        self.set_text_color(0, 0, 0)
        for x, ancho, titulo, alineacion in (
            (X_FECHA, X_COMPROBANTE - X_FECHA, 'FECHA', 'L'),
            (X_COMPROBANTE, X_DEBE - X_COMPROBANTE, 'COMPROBANTE Y DETALLE', 'L'),
            (X_DEBE, ANCHO_IMPORTE, 'DEBE', 'C'),
            (X_HABER, ANCHO_IMPORTE, 'HABER', 'C'),
            (X_SALDO, ANCHO_IMPORTE, 'SALDO', 'C'),
        ):
            self.set_xy(x + (1 if alineacion == 'L' else 0), self.y_grilla)
            self.cell(ancho, ALTO_CABECERA_TABLA, titulo, 0, 0, alineacion)

        # Caja de la tabla y filetes verticales que encolumnan los importes: son
        # los que hacen que el resumen se lea como un libro rayado y no como una lista
        self.set_draw_color(0, 0, 0)
        self.set_line_width(0.2)
        self.rect(MARGEN, self.y_grilla, X_FIN - MARGEN, Y_LIMITE_FILAS - self.y_grilla)
        self.line(MARGEN, self.y_cabecera, X_FIN, self.y_cabecera)
        for x in (X_DEBE, X_HABER, X_SALDO):
            self.line(x, self.y_grilla, x, Y_LIMITE_FILAS)

    def footer(self):
        self.set_y(-14)
        self.set_font('Arial', '', 6.5)
        self.set_text_color(*GRIS_DATO)
        self.cell(110, 4, 'IMPORTES EXPRESADOS EN PESOS  ·  DOCUMENTO NO VÁLIDO COMO FACTURA', 0, 0, 'L')
        self.cell(0, 4, f'Página {self.page_no()} de {{nb}}', 0, 0, 'R')
        self.set_text_color(0, 0, 0)

    # ------------------------------------------------------------------ filas
    def _dibujar_movimientos(self):
        """Dibuja las filas paginando a mano y devuelve la altura donde terminaron."""
        if not self.movimientos:
            self.set_font('Arial', '', 9)
            self.set_text_color(*GRIS_DATO)
            # Centrado solo en la franja de texto: cruzarlo sobre las columnas de
            # importes lo partiria con los filetes verticales
            self.set_xy(MARGEN, self.y_cabecera + 6)
            self.cell(X_DEBE - MARGEN, 6, 'Sin movimientos registrados en el período seleccionado.', 0, 0, 'C')
            self.set_text_color(0, 0, 0)
            return self.y_cabecera + 20

        y = self.y_cabecera
        for movimiento in self.movimientos:
            if y + ALTO_FILA > Y_LIMITE_FILAS:
                self.add_page()
                y = self.y_cabecera
            self._dibujar_fila(y, movimiento)
            y += ALTO_FILA

            # Los productos se despliegan debajo de su operacion. Una operacion
            # larga puede cortarse entre paginas; al retomar repito el numero de
            # comprobante para que ningun producto quede sin referencia arriba.
            for item in movimiento.get("items", ()):
                if y + ALTO_ITEM > Y_LIMITE_FILAS:
                    self.add_page()
                    y = self.y_cabecera
                    self._dibujar_continuacion(y, movimiento)
                    y += ALTO_ITEM
                self._dibujar_item(y, item)
                y += ALTO_ITEM

            self._separador(y)
        return y

    def _cerrar_tabla(self, y_final):
        """Cierra la grilla justo debajo de la ultima fila de la pagina final.

        La cabecera dibuja los filetes hasta el pie porque no sabe cuantas filas
        van a entrar; aca tapo con blanco el tramo que quedo sin usar, para que el
        resumen termine donde terminan los movimientos y no con media hoja rayada.
        """
        if y_final >= Y_LIMITE_FILAS:
            return

        self.set_fill_color(255, 255, 255)
        self.rect(MARGEN - 0.5, y_final + 0.15, X_FIN - MARGEN + 1, Y_LIMITE_FILAS - y_final + 0.5, 'F')

        self.set_draw_color(0, 0, 0)
        self.set_line_width(0.2)
        self.line(MARGEN, y_final, X_FIN, y_final)

    def _dibujar_fila(self, y, movimiento):
        # Los datos de cada movimiento van +2 y en negro para leerse mas fuerte
        self.set_font('Arial', '', 10)
        self.set_text_color(0, 0, 0)

        """La fecha cierra con un guion medio que la ata al comprobante: se leen
        como un solo encabezado ("06/09/2026 - Venta Nro 00004") aunque cada uno
        siga en su columna. La escribo midiendo su ancho y arrancando desde el
        final, asi el guion queda siempre a la misma distancia del comprobante y
        no colgado a media columna."""
        fecha = f"{self._fecha_corta(movimiento['fecha'])} -"
        ancho_fecha = self.get_string_width(fecha)
        self.set_xy(X_COMPROBANTE - 1.5 - ancho_fecha, y)
        self.cell(ancho_fecha, ALTO_FILA, fecha, 0, 0, 'L')

        """El detalle de los movimientos sin productos (pagos, fletes, cobros) va
        pegado al comprobante en el mismo renglon: es una linea corta y abrir un
        renglon aparte para ella estiraria el resumen sin necesidad."""
        ancho = X_DEBE - X_COMPROBANTE - 2
        texto = movimiento['comprobante']
        if movimiento['detalle']:
            texto = f"{texto} - {movimiento['detalle']}"

        self.set_xy(X_COMPROBANTE + 1, y)
        self.set_text_color(0, 0, 0)
        self.cell(ancho, ALTO_FILA, self._recortar(texto, ancho), 0, 0, 'L')

        # Debe y Haber solo se imprimen cuando la fila los mueve: la columna vacia
        # es la que deja ver de un vistazo si el movimiento sumo o resto
        self.set_text_color(0, 0, 0)
        self._importe(X_DEBE, y, movimiento['debe'])
        self._importe(X_HABER, y, movimiento['haber'])

        saldo = _formato_importe(movimiento['saldo'])
        self._fuente_que_entra(saldo, ANCHO_IMPORTE - 2, 'B', 10)
        self.set_xy(X_SALDO, y)
        self.cell(ANCHO_IMPORTE - 2, ALTO_FILA, saldo, 0, 0, 'R')

    def _dibujar_item(self, y, item):
        """Escribe un producto de la operacion: nombre a la izquierda y su
        subtotal a la derecha, alineados con el comprobante que los agrupa."""
        x_texto = X_COMPROBANTE + 1
        x_subtotal = X_DEBE - 2 - ANCHO_SUBTOTAL_ITEM
        ancho_texto = x_subtotal - x_texto - 2

        self.set_text_color(0, 0, 0)
        self.set_font('Arial', '', 9)
        self.set_xy(x_texto, y)
        self.cell(ancho_texto, ALTO_ITEM, self._recortar(item['texto'], ancho_texto), 0, 0, 'L')

        subtotal = _formato_importe(item['subtotal'])
        self._fuente_que_entra(subtotal, ANCHO_SUBTOTAL_ITEM, '', 9)
        self.set_xy(x_subtotal, y)
        self.cell(ANCHO_SUBTOTAL_ITEM, ALTO_ITEM, subtotal, 0, 0, 'R')
        self.set_text_color(0, 0, 0)

    def _dibujar_continuacion(self, y, movimiento):
        """Reencabeza los productos de una operacion que sigue en otra pagina."""
        self.set_font('Arial', 'I', 7)
        self.set_text_color(*GRIS_DATO)
        self.set_xy(X_COMPROBANTE + 1, y)
        self.cell(X_DEBE - X_COMPROBANTE - 2, ALTO_ITEM,
                  f"{movimiento['comprobante']} (continúa)", 0, 0, 'L')
        self.set_text_color(0, 0, 0)

    def _separador(self, y):
        """Renglon gris claro que cierra el movimiento con todos sus productos.

        Va debajo del ultimo producto y no de la fila de la operacion, asi el
        encabezado y su detalle se leen como un solo bloque.
        """
        if y >= Y_LIMITE_FILAS:
            return
        self.set_draw_color(*GRIS_LINEA)
        self.set_line_width(0.1)
        self.line(MARGEN, y, X_FIN, y)
        self.set_draw_color(0, 0, 0)

    def _importe(self, x, y, valor):
        if not valor:
            return
        texto = _formato_importe(valor)
        self._fuente_que_entra(texto, ANCHO_IMPORTE - 2, '', 10)
        self.set_xy(x, y)
        self.cell(ANCHO_IMPORTE - 2, ALTO_FILA, texto, 0, 0, 'R')

    # ----------------------------------------------------------------- totales
    def _dibujar_totales(self, y_final):
        y = y_final + 4
        self.set_draw_color(0, 0, 0)
        self.set_line_width(0.4)
        self.rect(MARGEN, y, X_FIN - MARGEN, 16)

        # Izquierda: cuantos movimientos entraron y a favor de quien quedo el saldo
        self.set_font('Arial', 'B', 8)
        self.set_text_color(0, 0, 0)
        self.set_xy(MARGEN + 3, y + 3)
        self.cell(60, 4, f'MOVIMIENTOS DEL PERÍODO: {len(self.movimientos)}', 0, 0, 'L')

        self.set_font('Arial', '', 8)
        self.set_text_color(*GRIS_DATO)
        self.set_xy(MARGEN + 3, y + 9)
        self.cell(90, 4, self._leyenda_saldo(), 0, 0, 'L')

        # Derecha: los totales, encolumnados bajo las mismas columnas de la tabla
        for x, etiqueta, valor in (
            (X_DEBE, 'TOTAL DEBE', self.totales['debe']),
            (X_HABER, 'TOTAL HABER', self.totales['haber']),
            (X_SALDO, 'SALDO FINAL', self.totales['saldo']),
        ):
            self.set_font('Arial', '', 6.5)
            self.set_text_color(*GRIS_DATO)
            self.set_xy(x, y + 2.5)
            self.cell(ANCHO_IMPORTE - 2, 3.5, etiqueta, 0, 0, 'R')

            texto = _formato_importe(valor)
            self._fuente_que_entra(texto, ANCHO_IMPORTE - 2, 'B', 12 if x == X_SALDO else 10.5)
            self.set_text_color(*(self._color_saldo(valor) if x == X_SALDO else (0, 0, 0)))
            self.set_xy(x, y + 7)
            self.cell(ANCHO_IMPORTE - 2, 5, texto, 0, 0, 'R')

        """Aclaracion al pie del saldo final: con arrastre, Total Debe menos
        Total Haber no da el saldo final (la diferencia es justo el saldo
        anterior) y sin la leyenda se lee como una cuenta mal hecha."""
        if self.saldo_anterior:
            self.set_font('Arial', 'I', 6)
            self.set_text_color(*GRIS_DATO)
            self.set_xy(X_SALDO - 20, y + 11.5)
            self.cell(ANCHO_IMPORTE + 18, 3, 'incluye el saldo anterior', 0, 0, 'R')

        self.set_text_color(0, 0, 0)

    def _leyenda_saldo(self):
        saldo = self.totales['saldo']
        if not self.movimientos and not saldo:
            return 'No hubo movimientos en el período.'
        if saldo > 0:
            return 'Saldo deudor: el cliente adeuda este importe.'
        if saldo < 0:
            return 'Saldo acreedor: el importe queda a favor del cliente.'
        return 'Cuenta saldada en el período.'

    # ----------------------------------------------------------------- helpers
    def _texto_periodo(self):
        if self.desde and self.hasta:
            return f'{self._fecha_corta(self.desde)} al {self._fecha_corta(self.hasta)}'
        if self.desde:
            return f'desde el {self._fecha_corta(self.desde)}'
        if self.hasta:
            return f'hasta el {self._fecha_corta(self.hasta)}'
        return 'historial completo'

    @staticmethod
    def _fecha_corta(fecha):
        return fecha.strftime('%d/%m/%Y') if hasattr(fecha, 'strftime') else str(fecha or '')

    def _fuente_que_entra(self, texto, ancho_max, estilo, size_inicial, size_minimo=5.5):
        """Deja activa la fuente mas grande con la que el texto entra en su celda.

        Los importes no se pueden recortar como un texto: un saldo de ocho cifras
        tiene que leerse entero, asi que cuando no entra en la columna achico el
        cuerpo en vez de cortar digitos.
        """
        size = size_inicial
        self.set_font('Arial', estilo, size)
        while size > size_minimo and self.get_string_width(texto) > ancho_max:
            size -= 0.25
            self.set_font('Arial', estilo, size)

    def _recortar(self, texto, ancho_max):
        """Recorta el texto al ancho de su columna, cerrando con puntos suspensivos."""
        texto = _latin1(texto)
        if self.get_string_width(texto) <= ancho_max:
            return texto
        while texto and self.get_string_width(texto + '...') > ancho_max:
            texto = texto[:-1]
        return texto + '...'

    def generate_pdf(self, path=None):
        self.add_page()
        y_final = self._dibujar_movimientos()
        self._cerrar_tabla(y_final)
        self._dibujar_totales(y_final)
        return _salida_pdf(self, path)
