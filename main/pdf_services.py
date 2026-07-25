from fpdf import FPDF

# Ancho en mm de la columna DETALLE: el valor normal deja lugar a la columna
# de subtotales; el "solo" ocupa tambien ese espacio cuando no hay importes
ANCHO_DETALLE = 86
ANCHO_DETALLE_SOLO = 121.5

# Tope de caracteres del detalle para que no invada la columna siguiente ni el
# borde del comprobante, proporcional al ancho disponible en cada caso
CHARS_DETALLE = 48
CHARS_DETALLE_SOLO = 67


def _formato_moneda(valor):
    # Formato argentino: punto para los miles y coma para los decimales
    # ("$ 12.100,00"). Convierto el separador estándar de Python al criterio local.
    try:
        s = f"{float(valor or 0):,.2f}"
    except (TypeError, ValueError):
        s = "0.00"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"$ {s}"


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

        self.set_text_color(80, 80, 80) # Gris oscuro para la fecha
        self.set_xy(offset_x + 90, 36)
        self.cell(12, 6, str(d)[:2], 0, 0, 'C')
        self.set_xy(offset_x + 104, 36)
        self.cell(12, 6, str(m)[:2], 0, 0, 'C')
        self.set_xy(offset_x + 118, 36)
        self.cell(16, 6, str(y)[:4], 0, 0, 'C')
        self.set_text_color(0, 0, 0) # Volver a negro para las etiquetas

        # Datos del Cliente
        self.set_font('Arial', '', 9)

        # Señor/a
        self.set_xy(offset_x + 5, 47)
        self.set_text_color(0, 0, 0) # Negro para etiquetas
        self.cell(self.get_string_width(' Señor/a: '), 6, ' Señor/a: ')
        self.set_text_color(80, 80, 80) # Gris oscuro para datos
        self.cell(0, 6, f'{self.nombre} {self.apellido}')
        self.line(offset_x + 5, 54, offset_x + 143.5, 54)

        # Fila 2: CUIT y Teléfono (intercambiada con Domicilio)
        # CUIT a la izquierda
        self.set_xy(offset_x + 5, 55)
        self.set_text_color(0, 0, 0)
        label_cuit = " CUIT: "
        self.cell(self.get_string_width(label_cuit), 6, label_cuit)
        self.set_text_color(80, 80, 80)
        self.cell(0, 6, f'{self.cuit if self.cuit else ""}')

        # Teléfono desde la mitad (138.5 / 2 = 69.25)
        self.set_xy(offset_x + 5 + 69.25, 55)
        self.set_text_color(0, 0, 0)
        label_tel = " Teléfono: "
        self.cell(self.get_string_width(label_tel), 6, label_tel)
        self.set_text_color(80, 80, 80)
        self.cell(0, 6, f'{self.telefono if self.telefono else ""}')

        self.line(offset_x + 5, 62, offset_x + 143.5, 62)

        # Fila 3: Domicilio
        self.set_xy(offset_x + 5, 63)
        self.set_text_color(0, 0, 0)
        self.cell(self.get_string_width(' Domicilio: '), 6, ' Domicilio: ')
        self.set_text_color(80, 80, 80)
        dir_str = self.direccion if self.direccion else ""
        loc_str = self.localidad if self.localidad else ""
        domicilio_val = f'{dir_str}' + (f' - {loc_str}' if loc_str else '')
        self.cell(0, 6, domicilio_val)
        self.line(offset_x + 5, 70, offset_x + 143.5, 70)

        # Reset color para encabezados de tabla
        self.set_text_color(0, 0, 0)

        # Fila 4: Observaciones (debajo del domicilio). La etiqueta se imprime
        # siempre; el texto va en gris y se parte en hasta 3 lineas
        self.set_font('Arial', 'B', 9)
        self.set_xy(offset_x + 5, 71)
        self.set_text_color(0, 0, 0)
        self.cell(self.get_string_width(' Observaciones: '), 4, ' Observaciones: ')

        self.set_font('Arial', '', 8)
        self.set_text_color(80, 80, 80)
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

            self.set_font('Arial', '', 9)
            self.set_text_color(80, 80, 80) # Datos de productos en gris oscuro

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

        self.set_font('Arial', 'B', 11)
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
        if path:
            return self.output(path)
        else:
            try:
                salida = self.output()
                return bytes(salida) if isinstance(salida, bytearray) else salida
            except TypeError:
                return self.output(dest='S').encode('latin1')
