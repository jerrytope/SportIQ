from django import forms
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm

from apps.catalog.models import Profession, Sport

from .models import User


class SignupForm(forms.ModelForm):
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
                                help_text="At least 8 characters; not entirely numeric.")
    password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    professions = forms.ModelMultipleChoiceField(
        queryset=Profession.objects.all(), widget=forms.CheckboxSelectMultiple, required=True,
        label="I am a…", help_text="Choose all that apply. We use this to recommend courses.",
    )
    accept_terms = forms.BooleanField(label="I agree to the Terms of use and have read the Privacy notice (NDPA 2023)")
    marketing = forms.BooleanField(required=False, label="Send me the SportIQ newsletter")

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "phone", "state"]
        labels = {"phone": "Phone (for SMS reminders, optional)", "state": "State"}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["state"].required = True
        self.fields["email"].widget.attrs["autocomplete"] = "email"

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists. Try logging in.")
        return email

    def clean(self):
        data = super().clean()
        p1, p2 = data.get("password1"), data.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Passwords do not match.")
        if p1:
            tmp = User(email=data.get("email", ""), first_name=data.get("first_name", ""))
            try:
                password_validation.validate_password(p1, tmp)
            except forms.ValidationError as e:
                self.add_error("password1", e)
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
            user.professions.set(self.cleaned_data["professions"])
        return user


class LoginForm(AuthenticationForm):
    username = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"autocomplete": "email", "autofocus": True}))


class ProfileForm(forms.ModelForm):
    professions = forms.ModelMultipleChoiceField(queryset=Profession.objects.all(),
                                                 widget=forms.CheckboxSelectMultiple, required=False)
    sports = forms.ModelMultipleChoiceField(queryset=Sport.objects.all(), widget=forms.CheckboxSelectMultiple,
                                            required=False)

    class Meta:
        model = User
        fields = ["first_name", "last_name", "photo", "phone", "state", "lga", "gender", "languages", "bio",
                  "professions", "sports", "profile_public"]
        widgets = {"bio": forms.Textarea(attrs={"rows": 4})}
        labels = {"profile_public": "Show my public professional profile (name, bio, verified credentials)"}


class PreferencesForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["notify_email", "notify_sms", "data_saver"]
        labels = {
            "notify_email": "Email notifications (enrolments, results, certificates, reminders)",
            "notify_sms": "SMS notifications for important events (needs a phone number)",
            "data_saver": "Data-saver mode: lower video quality, audio-first lessons, no autoplay",
        }


class SensitiveDataForm(forms.ModelForm):
    consent = forms.BooleanField(required=False, label="I consent to SportIQ using this information only for "
                                 "aggregated inclusion reporting and to provide accessibility support")

    class Meta:
        model = User
        fields = ["has_disability", "accessibility_needs"]
        widgets = {"has_disability": forms.NullBooleanSelect()}
        labels = {"has_disability": "Do you have a disability? (optional)",
                  "accessibility_needs": "Accessibility needs we should know about (optional)"}
