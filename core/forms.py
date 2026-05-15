from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import Channel, DirectMessage, Message

User = get_user_model()


def _discord_input(widget: forms.Widget) -> None:
    widget.attrs.setdefault(
        "class",
        "form-control bg-dark text-light border-secondary",
    )


class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Nazwa użytkownika"
        self.fields["password"].label = "Hasło"
        for field in self.fields.values():
            _discord_input(field.widget)


class RegisterForm(UserCreationForm):
    email = forms.EmailField(
        label="Adres e-mail",
        required=True,
        widget=forms.EmailInput(),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "password1", "password2")
        labels = {
            "username": "Nazwa użytkownika",
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["password1"].label = "Hasło"
        self.fields["password2"].label = "Potwierdzenie hasła"
        for name, field in self.fields.items():
            if name == "email":
                _discord_input(field.widget)
            elif name != "password1" and name != "password2":
                _discord_input(field.widget)
            else:
                field.widget.attrs.setdefault(
                    "class",
                    "form-control bg-dark text-light border-secondary",
                )

    def clean_username(self) -> str:
        username = self.cleaned_data.get("username") or ""
        username = User.normalize_username(username.strip())
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError(
                "Użytkownik o tej nazwie już istnieje. Wybierz inną nazwę.",
            )
        return username


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "avatar")
        labels = {
            "first_name": "Imię",
            "last_name": "Nazwisko",
            "email": "E-mail",
            "avatar": "Avatar",
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["avatar"].widget.attrs.setdefault(
            "class",
            "form-control bg-dark text-light border-secondary",
        )
        for name in ("first_name", "last_name", "email"):
            _discord_input(self.fields[name].widget)


class ChannelCreateForm(forms.ModelForm):
    class Meta:
        model = Channel
        fields = ("name",)
        labels = {"name": "Nazwa kanału"}

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        _discord_input(self.fields["name"].widget)

    def clean_name(self) -> str:
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError("Podaj nazwę kanału.")
        return name


class MessageForm(forms.ModelForm):
    class Meta:
        model = Message
        fields = ("content", "attachment")
        labels = {
            "content": "Wiadomość",
            "attachment": "Załącznik",
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["content"].required = False
        self.fields["attachment"].required = False
        _discord_input(self.fields["content"].widget)
        self.fields["content"].widget.attrs.setdefault("rows", 2)
        self.fields["attachment"].widget.attrs.setdefault(
            "class",
            "form-control form-control-sm bg-dark text-light border-secondary",
        )


class DirectMessageForm(forms.ModelForm):
    class Meta:
        model = DirectMessage
        fields = ("content", "attachment")
        labels = {
            "content": "Wiadomość",
            "attachment": "Załącznik (opcjonalnie)",
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["content"].required = False
        self.fields["attachment"].required = False
        _discord_input(self.fields["content"].widget)
        self.fields["content"].widget.attrs.setdefault("rows", 2)
        self.fields["attachment"].widget.attrs.setdefault(
            "class",
            "form-control form-control-sm bg-dark text-light border-secondary",
        )


class DirectConversationStartForm(forms.Form):
    username = forms.CharField(
        label="Nazwa użytkownika",
        max_length=150,
        widget=forms.TextInput(),
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        _discord_input(self.fields["username"].widget)

    def clean_username(self) -> str:
        name = (self.cleaned_data.get("username") or "").strip()
        if not name:
            raise forms.ValidationError("Podaj nazwę użytkownika.")
        return name
