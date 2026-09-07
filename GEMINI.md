## Directivas del Repositorio
- **Nunca** usar emojis en los comentarios ni en los commits
- **Nunca** agregar el coauthored con claude o gemini a mis commits
- Usar **EXCLUSIVAMENTE** el sistema de color `oklch` para cualquier declaración de color en CSS, HTML o JS (evitar Hexadecimal, RGB, HSL, etc).
- **Nunca** usar estilos en línea (inline) con CSS. Solo se usarán si ya se estaba usando Tailwind en el proyecto.
- **Siempre** responder en español.
- **Siempre** iniciar los mensajes de commit con letra mayúscula.
- **Siempre** que se estile un `input` de texto/fecha/número o un `textarea`, resetear `appearance: none` (con su prefijo `-webkit-appearance: none`). Safari/WebKit impone un render nativo (sombra interior, alto fijo, alineación propia en los `type="date"`) que ignora el estilo propio; Chrome/Brave no. Hay un reset global en `base.css` que ya cubre los tipos comunes.
- **Siempre** que un `input`, `textarea` o `select` lleve una fuente menor a 16px, mantener el piso de 16px en dispositivos táctiles: iOS/iPadOS hace zoom automático al enfocar campos con fuente menor. `base.css` ya lo fuerza con un `@media (pointer: coarse)`; no reducir ese piso ni pisarlo con `!important` propio.
- **Siempre** que un comentario en Python ocupe más de un renglón, escribirlo con triple comilla (`"""..."""`) en vez de varias líneas con `#`. Los comentarios de un solo renglón se mantienen con `#`.