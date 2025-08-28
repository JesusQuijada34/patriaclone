import sys
import random
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QFormLayout)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QPalette, QColor

class PatriaLogin(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        self.setWindowTitle('Acceso seguro a la plataforma Patria')
        self.setFixedSize(400, 500)

        # Configurar paleta de colores
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(255, 255, 255))
        palette.setColor(QPalette.WindowText, QColor(36, 41, 46))
        palette.setColor(QPalette.Base, QColor(255, 255, 255))
        palette.setColor(QPalette.Text, QColor(36, 41, 46))
        self.setPalette(palette)

        # Layout principal
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(30, 30, 30, 30)

        # Título
        title = QLabel('Acceso seguro a la plataforma Patria')
        title.setAlignment(Qt.AlignCenter)
        title_font = QFont('Segoe UI', 14, QFont.Bold)
        title.setFont(title_font)
        layout.addWidget(title)

        # Formulario
        form_layout = QFormLayout()
        form_layout.setSpacing(15)
        form_layout.setLabelAlignment(Qt.AlignLeft)

        # Cédula
        cedula_label = QLabel('Cédula')
        cedula_label.setStyleSheet("color: #586069; font-size: 14px; font-weight: 500;")
        self.cedula_input = QLineEdit()
        self.cedula_input.setPlaceholderText('Ej: 12345678')
        self.cedula_input.setMaxLength(12)
        self.cedula_input.setStyleSheet("""
            QLineEdit {
                padding: 8px;
                border: 1.5px solid #d1d5da;
                border-radius: 8px;
                font-size: 16px;
            }
            QLineEdit:focus {
                border-color: #c62828;
            }
        """)
        form_layout.addRow(cedula_label, self.cedula_input)

        # Captcha
        captcha_label = QLabel('Captcha')
        captcha_label.setStyleSheet("color: #586069; font-size: 14px; font-weight: 500;")

        captcha_layout = QHBoxLayout()
        self.captcha_display = QLabel()
        self.captcha_display.setFixedSize(180, 50)
        self.captcha_display.setStyleSheet("""
            QLabel {
                background-color: #f8f8f8;
                border: 1px solid #eee;
                border-radius: 4px;
                font-family: Consolas, Menlo, Monaco, monospace;
                font-size: 24px;
                qproperty-alignment: AlignCenter;
                letter-spacing: 4px;
            }
        """)

        self.refresh_btn = QPushButton('↻')
        self.refresh_btn.setFixedSize(30, 30)
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                color: #c62828;
                background: transparent;
                border: none;
                font-size: 18px;
            }
            QPushButton:hover {
                color: #8e0000;
            }
        """)
        self.refresh_btn.clicked.connect(self.generate_captcha)

        captcha_layout.addWidget(self.captcha_display)
        captcha_layout.addWidget(self.refresh_btn)

        captcha_widget = QWidget()
        captcha_widget.setLayout(captcha_layout)
        form_layout.addRow(captcha_label, captcha_widget)

        self.captcha_input = QLineEdit()
        self.captcha_input.setPlaceholderText('Ingrese el captcha')
        self.captcha_input.setMaxLength(6)
        self.captcha_input.setStyleSheet("""
            QLineEdit {
                padding: 8px;
                border: 1.5px solid #d1d5da;
                border-radius: 8px;
                font-size: 16px;
            }
            QLineEdit:focus {
                border-color: #c62828;
            }
        """)
        form_layout.addRow(QLabel(''), self.captcha_input)

        self.captcha_error = QLabel('Captcha incorrecto. Intente de nuevo.')
        self.captcha_error.setStyleSheet("color: #c62828; font-size: 14px;")
        self.captcha_error.hide()
        form_layout.addRow(QLabel(''), self.captcha_error)

        # Clave
        clave_label = QLabel('Clave de acceso')
        clave_label.setStyleSheet("color: #586069; font-size: 14px; font-weight: 500;")
        self.clave_input = QLineEdit()
        self.clave_input.setPlaceholderText('Ingrese su clave')
        self.clave_input.setMaxLength(32)
        self.clave_input.setEchoMode(QLineEdit.Password)
        self.clave_input.setStyleSheet("""
            QLineEdit {
                padding: 8px;
                border: 1.5px solid #d1d5da;
                border-radius: 8px;
                font-size: 16px;
            }
            QLineEdit:focus {
                border-color: #c62828;
            }
        """)
        form_layout.addRow(clave_label, self.clave_input)

        layout.addLayout(form_layout)

        # Botón de login
        self.login_btn = QPushButton('Entrar')
        self.login_btn.setStyleSheet("""
            QPushButton {
                background-color: #c62828;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #8e0000;
            }
        """)
        self.login_btn.clicked.connect(self.validate_form)
        layout.addWidget(self.login_btn)

        # Enlaces
        links_layout = QVBoxLayout()
        links_layout.setSpacing(8)
        links_layout.setAlignment(Qt.AlignCenter)

        forgot_clave = QLabel('<a href="#" style="color: #c62828; text-decoration: none; font-size: 14px;">¿Olvidó su clave?</a>')
        forgot_clave.setOpenExternalLinks(False)
        forgot_clave.linkActivated.connect(self.forgot_clave)

        forgot_usuario = QLabel('<a href="#" style="color: #c62828; text-decoration: none; font-size: 14px;">¿Olvidó su usuario?</a>')
        forgot_usuario.setOpenExternalLinks(False)
        forgot_usuario.linkActivated.connect(self.forgot_usuario)

        links_layout.addWidget(forgot_clave)
        links_layout.addWidget(forgot_usuario)

        layout.addLayout(links_layout)

        self.setLayout(layout)

        # Generar captcha inicial
        self.generate_captcha()

    def generate_captcha(self):
        chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789"
        self.current_captcha = ''.join(random.choice(chars) for _ in range(5))
        self.captcha_display.setText(self.current_captcha)
        self.captcha_error.hide()

    def validate_form(self):
        cedula = self.cedula_input.text().strip()
        captcha = self.captcha_input.text().strip()
        clave = self.clave_input.text()

        # Validar captcha
        if captcha.lower() != self.current_captcha.lower():
            self.captcha_error.show()
            self.generate_captcha()
            return

        # Aquí iría la lógica de validación real
        print(f"Cédula: {cedula}, Clave: {clave}")

    def forgot_clave(self):
        print("Redirigiendo a recuperar clave...")

    def forgot_usuario(self):
        print("Redirigiendo a recuperar usuario...")

if __name__ == '__main__':
    app = QApplication(sys.argv)

    # Establecer estilo de la aplicación
    app.setStyle('Fusion')

    window = PatriaLogin()
    window.show()

    sys.exit(app.exec_())
