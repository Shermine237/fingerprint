{
    'name': 'Pointeur HR',
    'version': '1.0',
    'category': 'Human Resources',
    'sequence': 80,
    'summary': 'Gestion des pointages des employés',
    'description': """
        Module de gestion des pointages des employés avec importation depuis un pointeur.
        
        Fonctionnalités :
        - Import des pointages depuis un fichier CSV
        - Gestion des lieux de pointage
        - Suivi des types de présence (heures supplémentaires, retard, départ anticipé)
        - Calcul automatique des heures basé sur le calendrier de l'employé
        - Rapport d'analyse des présences
        - Export des rapports en Excel et PDF
    """,
    'author': 'Shermine237',
    'website': 'https://github.com/Shermine237',
    'depends': [
        'hr_attendance',
        'hr',
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizards/hr_attendance_report_export_views.xml',
        'views/hr_employee_views.xml',
        'views/hr_attendance_views.xml',
        'views/hr_attendance_report_views.xml',
        'views/pointeur_location_views.xml',
        'views/pointeur_import_views.xml',
        'views/pointeur_hr_menus.xml',
        'reports/hr_attendance_report_template.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
