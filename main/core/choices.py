from django.db import models

class Region(models.TextChoices):
    ARARUAMA = "araruama", "Araruama"
    BARRA_MANSA = "barra-mansa", "Barra Mansa"
    CABO_FRIO = "cabo-frio", "Cabo Frio"
    CAMPOS = "campos", "Campos"
    CAXIAS = "caxias", "Caxias"
    ITABORAI = "itaborai", "Itaboraí"
    MARICA = "marica", "Maricá"
    NITEROI = "niteroi", "Niterói"
    PARAIBA_DO_SUL = "paraiba-do-sul", "Paraíba do Sul"
    PETROPOLIS = "petropolis", "Petrópolis"
    RESENDE = "resende", "Resende"
    RIO_BONITO = "rio-bonito", "Rio Bonito"
    RIO_DE_JANEIRO = "rio-de-janeiro", "Rio de Janeiro"
    RIO_ZONA_NORTE = "rio-zona-norte", "Rio (Zona Norte)"
    RIO_ZONA_SUL = "rio-zona-sul", "Rio (Zona Sul)"
    VOLTA_REDONDA = "volta-redonda", "Volta Redonda"