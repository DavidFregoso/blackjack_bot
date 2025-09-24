# Biblioteca de Plantillas para Reconocimiento de Cartas

Coloca en esta carpeta las imágenes de referencia utilizadas por `CardRecognizer`.

## Estructura

```
m1_ingesta/templates/
├── ranks/
│   ├── 2.png
│   ├── 3.png
│   ├── ...
│   ├── K.png
│   └── A.png
└── suits/
    ├── hearts.png
    ├── diamonds.png
    ├── clubs.png
    └── spades.png
```

Cada imagen debe estar preparada en alto contraste (preferiblemente blanco y negro)
y alineada según el mismo tamaño que aparecerá en pantalla. Estas imágenes se usarán
para realizar *template matching*, por lo que mantener la consistencia es crucial
para lograr buenos resultados.
