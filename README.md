# Interfaz de Acceso Plataforma Patria

Este proyecto replica la interfaz de acceso a la plataforma Patria utilizando Python y PyQt5.

## Características

- Interfaz gráfica idéntica a la página web original
- Validación de formulario con sistema de captcha
- Diseño limpio y responsive
- Sin dependencias de sombras o transiciones (limitaciones de QSS)

## Requisitos

- Python 3.6 o superior
- PyQt5 para la interfaz gráfica

## Instalación

1. Clona o descarga este repositorio
2. Instala las dependencias:

```bash
pip install -r lib-requirements.txt
```

## Ejecución

```bash
python patria_login.py
```

## Estructura del proyecto

```
patriaclone/
├── patriaclone.py    # Código principal de la aplicación
├── lib-requirements.txt   # Dependencias del proyecto
└── README.md          # Este archivo
```

## Funcionalidades

- Campo para ingresar cédula con validación
- Sistema de captcha generado aleatoriamente
- Campo para contraseña con ocultamiento de texto
- Validación básica del formulario
- Enlaces de recuperación de credenciales

## Notas

Esta es una interfaz gráfica de ejemplo que replica el diseño visual de la plataforma Patria. No establece conexión con servidores reales ni maneja datos reales de usuarios.
