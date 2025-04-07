# Copyright (c) 2023-2025, Abilian SAS

from __future__ import annotations

import re

from flask_security.forms import (
    ConfirmRegisterForm,
    get_form_field_label,
    password_required,
)
from flask_wtf import RecaptchaField
from wtforms import PasswordField, StringField, ValidationError
from wtforms.validators import DataRequired, Length


#
# Forms
#
def validate_password(form, field) -> None:
    msg = (
        "Le mot de passe doit comporter au moins 1 majuscule, 1 minuscule et 1 chiffre"
    )
    if not re.search("[0-9]", field.data):
        raise ValidationError(msg)
    if not re.search("[a-z]", field.data):
        raise ValidationError(msg)
    if not re.search("[A-Z]", field.data):
        raise ValidationError(msg)


password_length = Length(min=8, max=128, message="PASSWORD_INVALID_LENGTH")


#
# TODO: override similarly change password form
#
class ExtendedConfirmRegisterForm(ConfirmRegisterForm):
    nom = StringField("Nom", [DataRequired()])
    prenom = StringField("Prénom", [DataRequired()])
    organisme = StringField("Organisme", validators=[DataRequired()])
    code_postal = StringField("Code postal", validators=[DataRequired()])

    # Override password field from flask-security
    password = PasswordField(
        get_form_field_label("password"),
        validators=[password_required, password_length, validate_password],
    )
    recaptcha = RecaptchaField()
