from fpdf import FPDF


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
    def __init__(self, id_operacion, fecha, nombre, localidad, direccion, productos, apellido=" ", cuit=" ", telefono="", observaciones="", total=0):
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

        # Columnas: CANT. | DETALLE | SUBTOTAL
        self.set_font('Arial', 'B', 9)
        self.set_xy(offset_x + 5, 70)
        self.cell(17, 8, 'CANT.', 0, 0, 'C')
        self.set_xy(offset_x + 22, 70)
        self.cell(86, 8, 'DETALLE', 0, 0, 'C')
        self.set_xy(offset_x + 108, 70)
        self.cell(35.5, 8, 'SUBTOTAL', 0, 0, 'C')
        self.line(offset_x + 5, 78, offset_x + 143.5, 78)

        # Lineas verticales de la tabla (cortan en 193; la casilla de total las
        # tapa con relleno blanco sobre la ultima pagina)
        self.line(offset_x + 22, 70, offset_x + 22, 193)
        self.line(offset_x + 108, 70, offset_x + 108, 193)

    def draw_products(self):
        y_pos = 78
        for prod in self.productos:
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

            sub_str = _formato_moneda(subtotal)
            self.escribir_fila(0, y_pos, cant, detalle, sub_str)
            self.escribir_fila(148.5, y_pos, cant, detalle, sub_str)

            y_pos += 8
            self.set_text_color(0, 0, 0) # Líneas en negro
            self.line(5, y_pos, 143.5, y_pos)
            self.line(148.5 + 5, y_pos, 148.5 + 143.5, y_pos)

            # Corto antes para dejar el pie (casilla de total + observaciones/firma)
            if y_pos >= 182:
                self.add_page()
                y_pos = 78

        self.dibujar_total(0)
        self.dibujar_total(148.5)
        self.dibujar_observaciones(0)
        self.dibujar_observaciones(148.5)
        self.dibujar_firma(0)
        self.dibujar_firma(148.5)

    def escribir_fila(self, offset_x, y, c, d, s):
        self.set_xy(offset_x + 5, y)
        self.cell(17, 8, c, 0, 0, 'C')
        self.set_xy(offset_x + 22, y)
        # Detalle con limite de caracteres para no invadir la columna de subtotal
        self.cell(86, 8, f' {d[:48]}', 0, 0, 'L')
        self.set_xy(offset_x + 108, y)
        self.cell(34.5, 8, s, 0, 0, 'R')

    def dibujar_total(self, offset_x):
        """
        Casilla grande de total al pie del comprobante, alineada con la columna
        de subtotal y por encima de la franja de observaciones y firma.
        """
        self.set_auto_page_break(auto=False)

        # Relleno blanco para tapar las lineas de la grilla dentro de la casilla
        self.set_fill_color(255, 255, 255)
        self.set_draw_color(0, 0, 0)
        self.rect(offset_x + 78, 183, 65.5, 9.5, 'DF')

        self.set_text_color(0, 0, 0)
        self.set_font('Arial', 'B', 12)
        self.set_xy(offset_x + 81, 183)
        self.cell(28, 9.5, 'TOTAL', 0, 0, 'L')

        self.set_font('Arial', 'B', 13)
        self.set_xy(offset_x + 108, 183)
        self.cell(33, 9.5, _formato_moneda(self.total), 0, 0, 'R')

    def dibujar_observaciones(self, offset_x):
        """
        Franja inferior izquierda del comprobante (a la par del recuadro de
        firma): etiqueta "Observaciones:" siempre impresa, con la nota de la
        operación en gris o el espacio en blanco para completar a mano.
        """
        # La franja vive pegada al borde inferior: sin esto, la última línea
        # dispara el salto de página automático y rompe el comprobante
        self.set_auto_page_break(auto=False)

        # Separo la franja de la tabla de productos
        self.line(offset_x + 5, 193, offset_x + 103.5, 193)

        self.set_font('Arial', 'B', 7)
        self.set_text_color(0, 0, 0)
        self.set_xy(offset_x + 6, 193.5)
        self.cell(30, 3, 'Observaciones:', 0, 0, 'L')

        if not self.observaciones:
            self.set_auto_page_break(auto=True, margin=5)
            return

        # Texto en gris, partido a mano en hasta 3 lineas dentro de la franja
        # (193-205); si no entra, la ultima linea corta con elipsis
        self.set_font('Arial', '', 6)
        self.set_text_color(80, 80, 80)
        ancho_max = 95.5
        lineas = []
        linea = ''
        for palabra in self.observaciones.split():
            candidata = f'{linea} {palabra}'.strip()
            if self.get_string_width(candidata) <= ancho_max:
                linea = candidata
            else:
                if linea:
                    lineas.append(linea)
                # Palabra mas larga que la franja: se corta por caracteres
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

        y = 196.5
        for texto_linea in lineas:
            self.set_xy(offset_x + 6, y)
            self.cell(96.5, 2.6, texto_linea, 0, 0, 'L')
            y += 2.6

        self.set_text_color(0, 0, 0)
        self.set_auto_page_break(auto=True, margin=5)

    def dibujar_firma(self, offset_x):
        self.set_fill_color(255, 255, 255)
        # Dibujo el recuadro de firma
        self.rect(offset_x + 103.5, 193, 40, 12, "DF")

        self.set_font("Arial", "B", 7)
        self.set_text_color(0, 0, 0)
        
        # Posiciono el texto 'FIRMA' arriba del recuadro (y=193.5)
        self.set_xy(offset_x + 103.5, 193.5)
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
