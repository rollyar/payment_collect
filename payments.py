# -*- coding: utf8 -*-
# This file is part of the payment_collect module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from decimal import Decimal
import datetime
import StringIO
from trytond.pool import Pool
from trytond.transaction import Transaction
import logging

logger = logging.getLogger(__name__)


class PaymentMixIn(object):

    _EOL = '\r\n'
    _SEPARATOR = ';'
    csv_format = False
    monto_total = Decimal('0')
    cantidad_registros = 0
    filename = paymode_type = res = period = type = None
    #journal = 'CASH'

    def attach_collect(self):
        pool = Pool()
        Attachment = pool.get('ir.attachment')
        collect = self.create_collect()
        attach = Attachment()
        attach.name = '%s' % self.filename
        attach.resource = collect
        attach.data = ''.join(self.res)
        attach.save()
        return collect

    @classmethod
    def get_domain(cls, period):
        Config = Pool().get('account.configuration')
        config = Config(1)
        invoice_type = ['out']

        domain = [
            ('state', 'in', [config.when_collect_payment]),
            ('type', 'in', invoice_type),
            ('invoice_date', '>=', period.start_date),
            ('invoice_date', '<=', period.end_date),
            ]

        return domain

    @classmethod
    def get_order(cls):
        return [
                ('invoice_date', 'ASC'),
                ('id', 'ASC')
            ]

    def lista_campo_ordenados(self):
        """ Devuelve lista de campos ordenados """
        return []

    def a_texto(self, csv_format=False):
        """ Concatena los valores de los campos de la clase y los
        devuelve en una cadena de texto.
        """
        campos = self.lista_campo_ordenados()
        campos = [x for x in campos if x != '']
        separador = csv_format and self._SEPARATOR or ''
        return separador.join(campos) + self._EOL

    @classmethod
    def message_invoice(cls, invoices, collect_result, message, pay_amount,
            pay_date=None, journal=None):
        CollectTransaction = Pool().get('payment.collect.transaction')
        Configuration = Pool().get('account.configuration')
        config = Configuration(1)
        invoice, = invoices
        transaction = CollectTransaction()
        transaction.invoice = invoice
        transaction.pay_date = pay_date
        transaction.pay_amount = pay_amount
        if journal is None:
            journal = config.default_payment_collect_journal
        transaction.journal = journal
        transaction.party = invoice.party
        transaction.collect_result = collect_result
        transaction.collect_message = message
        transaction.save()
        return transaction

    @classmethod
    def pay_invoice(cls, invoice, amount_to_pay, pay_date=None, journal=None):
        logger.info("PAY INVOICE: invoice_id: "+repr(invoice.number))
        # Pagar la invoice
        pool = Pool()
        Currency = pool.get('currency.currency')
        Configuration = pool.get('account.configuration')
        MoveLine = pool.get('account.move.line')
        Date = Pool().get('ir.date')

        if pay_date is None:
            pay_date = Date.today()

        with Transaction().set_context(date=pay_date):
            amount = Currency.compute(invoice.currency,
                amount_to_pay, invoice.company.currency)

        # FIXME migrate 4.0?
        #if invoice.type in ('in_invoice', 'out_credit_note'):
        #    amount = -amount

        reconcile_lines, remainder = \
            invoice.get_reconcile_lines_for_amount(amount)

        config = Configuration(1)

        amount_second_currency = None
        second_currency = None
        if invoice.currency != invoice.company.currency:
            amount_second_currency = amount_to_pay
            second_currency = invoice.currency

        line = None
        pay_journal = None
        if config.default_payment_collect_journal and journal is None:
            pay_journal = config.default_payment_collect_journal
        else:
            pay_journal = journal
        if not invoice.company.currency.is_zero(amount):
            line = invoice.pay_invoice(amount,
                                       pay_journal, pay_date,
                                       invoice.number, amount_second_currency,
                                       second_currency)
        if remainder != Decimal('0.0'):
            return
        else:
            if line:
                reconcile_lines += [line]
            if reconcile_lines:
                MoveLine.reconcile(reconcile_lines)
        # Fin pagar invoice

    def create_collect(self):
        Collect = Pool().get('payment.collect')
        collect = Collect()
        collect.monto_total = self.monto_total
        collect.cantidad_registros = self.cantidad_registros
        collect.period = self.period
        collect.paymode_type = self.__name__
        #collect.origin = self
        collect.type = self.type
        collect.save()
        self.collect = collect
        return collect

    def _add_attach_to_collect(self, collect, return_file):
        Attachment = Pool().get('ir.attachment')
        return_file.seek(0)
        attach = Attachment()
        filename = collect.paymode_type + '-' + self.type + '-' + \
            datetime.date.today().strftime("%Y-%m-%d")
        attach = Attachment()
        attach.name = filename + '.txt'
        attach.resource = collect
        attach.data = return_file.read()
        attach.save()

    def return_collect(self, start, tabla_codigos = {}):
        self.type = 'return'
        self.return_file = StringIO.StringIO(start.return_file)
        self.period = start.period
        self.create_collect()
        self.invoices_id = {
            'accepted_invoices': [],
            'rejected_invoices': [],
            }
        self.codigo_retorno = {}
        self.tabla_codigos = tabla_codigos
        return []

    def get_format_date(self):
        pool = Pool()
        Lang = pool.get('ir.lang')
        return lambda value: Lang.strftime(value, 'es_AR', '%d/%m/%Y')

    def get_format_number(self):
        pool = Pool()
        Lang = pool.get('ir.lang')
        es_419 = Lang(
            decimal_point=',',
            thousands_sep='.',
            grouping='[]',
            )
        return lambda value: Lang.format(es_419, '%.2f', value)
