from django import forms
from django.db.models import Q
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _

from pretix.base.models import Item, Order, Organizer
from pretix.base.signals import register_payment_providers


class OrderFilterForm(forms.Form):
    query = forms.CharField(
        label=_('Search for…'),
        widget=forms.TextInput(attrs={
            'placeholder': _('Search for…'),
            'autofocus': 'autofocus'
        }),
        required=False
    )
    status = forms.ChoiceField(
        label=_('Order status'),
        choices=(
            ('', _('All orders')),
            ('p', _('Paid')),
            ('n', _('Pending')),
            ('o', _('Pending (overdue)')),
            ('e', _('Expired')),
            ('ne', _('Pending or expired')),
            ('c', _('Canceled')),
            ('r', _('Refunded')),
        ),
        required=False,
    )

    def filter_qs(self, qs):
        fdata = self.cleaned_data

        if fdata.get('query'):
            u = fdata.get('query')
            if "-" in u:
                code = (Q(event__slug__icontains=u.split("-")[0])
                        & Q(code__icontains=Order.normalize_code(u.split("-")[1])))
            else:
                code = Q(code__icontains=Order.normalize_code(u))
            qs = qs.filter(
                code
                | Q(email__icontains=u)
                | Q(positions__attendee_name__icontains=u)
                | Q(positions__attendee_email__icontains=u)
                | Q(invoice_address__name__icontains=u)
                | Q(invoice_address__company__icontains=u)
            )

        if fdata.get('status'):
            s = fdata.get('status')
            if s == 'o':
                qs = qs.filter(status=Order.STATUS_PENDING, expires__lt=now().replace(hour=0, minute=0, second=0))
            elif s == 'ne':
                qs = qs.filter(status__in=[Order.STATUS_PENDING, Order.STATUS_EXPIRED])
            else:
                qs = qs.filter(status=s)

        return qs

    @property
    def filtered(self):
        return self.is_valid() and any(self.cleaned_data.values())


class EventOrderFilterForm(OrderFilterForm):
    item = forms.ModelChoiceField(
        label=_('Products'),
        queryset=Item.objects.none(),
        required=False,
        empty_label=_('All products')
    )
    provider = forms.ChoiceField(
        label=_('Payment provider'),
        choices=[
            ('', _('All payment providers')),
        ],
        required=False,
    )

    def get_payment_providers(self):
        providers = []
        responses = register_payment_providers.send(self.event)
        for receiver, response in responses:
            provider = response(self.event)
            providers.append({
                'name': provider.identifier,
                'verbose_name': provider.verbose_name
            })
        return providers

    def __init__(self, *args, **kwargs):
        self.event = kwargs.pop('event')
        super().__init__(*args, **kwargs)
        self.fields['item'].queryset = self.event.items.all()
        self.fields['provider'].choices += [(p['name'], p['verbose_name']) for p in self.get_payment_providers()]

    def filter_qs(self, qs):
        fdata = self.cleaned_data
        qs = super().filter_qs(qs)

        if fdata.get('item'):
            qs = qs.filter(positions__item_id__in=(fdata.get('item'),))

        if fdata.get('provider'):
            qs = qs.filter(payment_provider=fdata.get('provider'))

        return qs


class OrderSearchFilterForm(OrderFilterForm):
    organizer = forms.ModelChoiceField(
        label=_('Organizer'),
        queryset=Organizer.objects.none(),
        required=False,
        empty_label=_('All organizers')
    )

    def __init__(self, *args, **kwargs):
        request = kwargs.pop('request')
        super().__init__(*args, **kwargs)
        if request.user.is_superuser:
            self.fields['organizer'].queryset = Organizer.objects.all()
        else:
            self.fields['organizer'].queryset = Organizer.objects.filter(
                pk__in=request.user.teams.values_list('organizer', flat=True)
            )

    def filter_qs(self, qs):
        fdata = self.cleaned_data
        qs = super().filter_qs(qs)

        if fdata.get('organizer'):
            qs = qs.filter(event__organizer=fdata.get('organizer'))

        return qs
