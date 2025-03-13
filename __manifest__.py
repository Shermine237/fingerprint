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
        - Suivi des types de présence (normal, retard, départ anticipé, heures supplémentaires)
        - Calcul automatique des heures (normales, supplémentaires, retard, départ anticipé)
        - Rapport d'analyse des présences
    """,
    'author': 'Shermine237',
    'website': 'https://github.com/Shermine237',
    'depends': [
        'hr_attendance',
        'hr',
        'resource',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/pointeur_attendance_type_data.xml',
        'views/pointeur_location_views.xml',
        'views/pointeur_import_views.xml',
        'views/pointeur_attendance_type_views.xml',
        'views/hr_attendance_views.xml',
        'views/hr_employee_views.xml',
        'views/hr_attendance_report_views.xml',
        'views/pointeur_hr_menus.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
