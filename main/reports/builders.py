from itertools import groupby
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import CondPageBreak, Spacer, Table, TableStyle
from core.choices import Region
from core.formatters import format_cep, format_cpf, format_phone, format_sus
from patients.models import Color, Sex
from . import pdf


WEEKDAYS = [
    "Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira",
    "Sexta-feira", "Sábado", "Domingo",
]


def _label(choices_class, value):
    return dict(choices_class.choices).get(value, value)


def _plural(n, singular, plural):
    return f"{n} {singular if n == 1 else plural}"


def _footer(user):
    return f"Gerado em {timezone.localtime():%d/%m/%Y %H:%M} por {user.username}"


def _count_text(patients, companions):
    return (
        f"{_plural(patients, 'paciente', 'pacientes')} + "
        f"{_plural(companions, 'acompanhante', 'acompanhantes')} = "
        f"{_plural(patients + companions, 'pessoa', 'pessoas')}"
    )



def build_route_sheet(route, user):
    appointments = list(
        route.appointments.select_related("patient")
        .prefetch_related("companions")
        .order_by("appointment_time", "patient__name")
    )
    people = sum(1 + len(a.companions.all()) for a in appointments)
    vehicle, motorist = route.vehicle, route.motorist

    info = Table(
        [
            [pdf.p("Data", pdf.LABEL),
             pdf.p(f"{route.date:%d/%m/%Y} ({WEEKDAYS[route.date.weekday()]})"),
             pdf.p("Horário de saída", pdf.LABEL),
             pdf.p(f"{route.departure_time:%H:%M}")],
            [pdf.p("Região", pdf.LABEL),
             pdf.p(route.get_region_display()),
             pdf.p("Lotação", pdf.LABEL),
             pdf.p(f"{people} de {vehicle.seats} vagas")],
            [pdf.p("Veículo", pdf.LABEL),
             pdf.p(f"{vehicle.get_vehicle_type_display()} – {vehicle.plate}"),
             pdf.p("Motorista", pdf.LABEL),
             pdf.p(f"{motorist.name} – {format_phone(motorist.phone)}")],
        ],
        colWidths=[2.6 * cm, 10.4 * cm, 3.2 * cm, 10.5 * cm],
    )
    info.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))

    rows, number = [], 0
    for a in appointments:
        boarding = a.boarding_place + (f"\n{a.neighborhood}" if a.neighborhood else "")
        time = f"{a.appointment_time:%H:%M}"
        notes = ["Comorbidade"] if a.has_comorbidity else []
        if a.notes:
            notes.append(a.notes)

        number += 1
        rows.append([
            pdf.cell(number), pdf.cell(a.patient.name), pdf.cell(format_phone(a.patient.phone)),
            pdf.cell(boarding), pdf.cell(a.destination), pdf.cell(time), pdf.cell(". ".join(notes)),
        ])
        for companion in a.companions.all():
            number += 1
            rows.append([
                pdf.cell(number), pdf.cell(f"{companion.name} (acompanhante)"),
                pdf.cell(format_phone(companion.phone)), pdf.cell(boarding),
                pdf.cell(a.destination), pdf.cell(time), pdf.cell(f"Acompanha: {a.patient.name}"),
            ])

    story = [pdf.p("Planilha de rota", pdf.TITLE), info, Spacer(1, 10)]
    if rows:
        story.append(pdf.data_table(
            ["Nº", "Nome", "Telefone", "Embarque", "Destino", "Consulta", "Observações"],
            rows,
            [0.9 * cm, 5.0 * cm, 2.6 * cm, 5.2 * cm, 4.2 * cm, 1.7 * cm, 7.1 * cm],
        ))
    else:
        story.append(pdf.p("Nenhum paciente agendado nesta rota."))

    return pdf.render_pdf(
        story, title=f"Planilha de rota – {route.date:%d/%m/%Y}",
        footer=_footer(user), wide=True,
    )


def _record_row(r):
    documents = []
    if r.cpf:
        documents.append(format_cpf(r.cpf))
    if r.sus:
        documents.append(f"SUS {format_sus(r.sus)}")
    return [
        pdf.cell(r.name + (" (acompanhante)" if r.is_companion else "")),
        pdf.cell(format_phone(r.phone)),
        pdf.cell(f"{r.street}, {r.house_number} – {r.city}"),
        pdf.cell(r.neighborhood),
        pdf.cell(format_cep(r.cep)),
        pdf.cell("\n".join(documents)),
        pdf.cell(f"{r.birth_date:%d/%m/%Y}"),
        pdf.cell(r.destination),
        pdf.cell(_label(Color, r.color)),
        pdf.cell(_label(Sex, r.sex)),
    ]


def build_patients_report(records, *, start, end, filter_lines, user):
    story = [
        pdf.p("Relação de pacientes transportados", pdf.TITLE),
        pdf.p(f"Período: {start:%d/%m/%Y} a {end:%d/%m/%Y}"),
        pdf.p("Filtros: " + (" · ".join(filter_lines) if filter_lines else "nenhum")),
    ]
    totals = {"routes": 0, "patients": 0, "companions": 0}

    for day, day_records in groupby(records, key=lambda r: r.route_date):
        story.append(CondPageBreak(5 * cm))
        story.append(pdf.p(f"{WEEKDAYS[day.weekday()]}, {day:%d/%m/%Y}", pdf.H2))

        for _route_id, route_records in groupby(day_records, key=lambda r: r.route_id):
            items = list(route_records)
            first = items[0]
            patients = sum(1 for r in items if not r.is_companion)
            companions = len(items) - patients

            story.append(CondPageBreak(4 * cm))
            story.append(pdf.p(
                f"{first.departure_time:%H:%M} – {_label(Region, first.region)} – "
                f"{first.vehicle_type} ({first.vehicle_plate}) – Motorista: {first.motorist_name}",
                pdf.H3,
            ))
            story.append(pdf.data_table(
                ["Nome", "Telefone", "Endereço", "Bairro", "CEP", "CPF / SUS",
                 "Nascimento", "Destino", "Cor", "Sexo"],
                [_record_row(r) for r in items],
                [4.2 * cm, 2.3 * cm, 4.0 * cm, 2.6 * cm, 1.7 * cm, 2.9 * cm,
                 1.9 * cm, 2.6 * cm, 1.6 * cm, 1.6 * cm],
            ))
            story.append(pdf.p(f"Total da rota: {_count_text(patients, companions)}", pdf.RIGHT))

            totals["routes"] += 1
            totals["patients"] += patients
            totals["companions"] += companions

    story.append(CondPageBreak(5 * cm))
    story.append(Spacer(1, 10))
    story.append(pdf.data_table(
        ["Resumo do período", "Total"],
        [
            [pdf.cell("Rotas"), pdf.cell(totals["routes"])],
            [pdf.cell("Pacientes transportados"), pdf.cell(totals["patients"])],
            [pdf.cell("Acompanhantes"), pdf.cell(totals["companions"])],
            [pdf.cell("Total de pessoas"), pdf.cell(totals["patients"] + totals["companions"])],
        ],
        [8 * cm, 3 * cm],
        zebra=False,
    ))

    return pdf.render_pdf(
        story, title="Relação de pacientes transportados",
        footer=_footer(user), wide=True,
    )


def build_fleet_report(vehicles, *, type_label, user):
    vehicles = list(vehicles)
    operational = sum(1 for v in vehicles if v.is_operational)
    rows = [
        [
            pdf.cell(i), pdf.cell(v.get_vehicle_type_display()), pdf.cell(v.plate),
            pdf.cell(v.seats), pdf.cell("Funcionando" if v.is_operational else "Não funcionando"),
        ]
        for i, v in enumerate(vehicles, start=1)
    ]
    story = [
        pdf.p("Relação da frota", pdf.TITLE),
        pdf.p(f"Tipo de veículo: {type_label}"),
        pdf.p(
            f"Total de veículos: {len(vehicles)} "
            f"({operational} funcionando, {len(vehicles) - operational} não funcionando)",
            pdf.LABEL,
        ),
        Spacer(1, 8),
        pdf.data_table(
            ["Nº", "Tipo", "Placa", "Vagas", "Situação"],
            rows,
            [1.2 * cm, 6 * cm, 3 * cm, 2.5 * cm, 4.5 * cm],
        ),
    ]
    return pdf.render_pdf(story, title="Relação da frota", footer=_footer(user))