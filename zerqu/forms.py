# coding: utf-8


from flask import request
from werkzeug.datastructures import MultiDict
from flask_wtf import Form as BaseForm
from flask_wtf.recaptcha import RecaptchaField
from wtforms.fields import StringField, PasswordField
from wtforms.fields import SelectField, TextAreaField
from wtforms.validators import DataRequired, Email
from wtforms.validators import StopValidation
from .models import db, User, Cafe
from .errors import FormError


class Form(BaseForm):
    @classmethod
    def create_api_form(cls, obj=None):
        form = cls(MultiDict(request.get_json()), obj=obj, csrf_enabled=False)
        if not form.validate():
            raise FormError(form)
        return form


class UserForm(Form):
    username = StringField(validators=[DataRequired()])
    password = PasswordField(validators=[DataRequired()])


class UserProfileForm(Form):
    description = StringField()


class RegisterForm(UserForm):
    email = StringField(validators=[DataRequired(), Email()])

    def validate_username(self, field):
        if User.cache.filter_first(username=field.data):
            raise StopValidation('Username has been registered.')

    def validate_email(self, field):
        if User.cache.filter_first(email=field.data):
            raise StopValidation('Email has been registered.')

    def create_user(self):
        user = User(
            username=self.username.data,
            email=self.email.data,
        )
        user.password = self.password.data
        with db.auto_commit():
            db.session.add(user)
        return user


class RecaptchaForm(RegisterForm):
    recaptcha = RecaptchaField()


CAFE_PERMISSIONS = Cafe.PERMISSIONS.keys()


class CafeForm(Form):
    # TODO: validators
    name = StringField()
    slug = StringField()
    content = TextAreaField()
    # TODO: multiple choices
    permission = SelectField(choices=zip(CAFE_PERMISSIONS, CAFE_PERMISSIONS))
    # features

    def validate_slug(self, field):
        if Cafe.cache.filter_first(slug=field.data):
            raise StopValidation('Slug has been registered')

    def validate_name(self, field):
        if Cafe.cache.filter_first(name=field.data):
            raise StopValidation('Name has been registered')

    def create_cafe(self, user_id):
        cafe = Cafe(
            name=self.name.data,
            slug=self.slug.data,
            content=self.content.data,
            permission=Cafe.PERMISSIONS[self.permission.data],
            user_id=user_id,
        )
        with db.auto_commit():
            db.session.add(cafe)
        return cafe

    def update_cafe(self, cafe, user_id):
        # Only owner can change slug
        if user_id == cafe.user_id:
            keys = ['name', 'slug', 'content']
        else:
            keys = ['name', 'content']

        for k in keys:
            value = self.data.get(k)
            if value:
                setattr(cafe, k, value)

        cafe.permission = Cafe.PERMISSIONS[self.permission.data]
        with db.auto_commit():
            db.session.add(cafe)
        return cafe
