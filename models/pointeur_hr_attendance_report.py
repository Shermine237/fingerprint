from odoo import api, fields, models, tools
from datetime import datetime, timedelta
import pytz
import base64
import xlsxwriter
import io

class PointeurHrAttendanceReport(models.Model):
    _name = 'pointeur_hr.attendance.report'
    _description = 'Rapport de présence'
    _auto = False
    _order = 'date desc, employee_id'

    name = fields.Char(string='Nom', readonly=True)
    date = fields.Date(string='Date', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Employé', readonly=True)
    department_id = fields.Many2one('hr.department', string='Département', readonly=True)
    location_id = fields.Many2one('pointeur_hr.location', string='Lieu de pointage', readonly=True)
    default_location_id = fields.Many2one('pointeur_hr.location', string='Lieu par défaut', readonly=True)
    source = fields.Selection([
        ('manual', 'Manuel'),
        ('import', 'Import')
    ], string='Source', readonly=True)
    check_in = fields.Datetime(string='Entrée', readonly=True)
    check_out = fields.Datetime(string='Sortie', readonly=True)
    attendance_type_ids = fields.Char(string='Types de présence', readonly=True)
    working_hours = fields.Float(string='Heures travaillées', readonly=True)
    regular_hours = fields.Float(string='Heures normales', readonly=True)
    overtime_hours = fields.Float(string='Heures supplémentaires', readonly=True)
    late_hours = fields.Float(string='Heures de retard', readonly=True)
    early_leave_hours = fields.Float(string='Heures de départ anticipé', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        # Vérifier si la colonne default_location_id existe dans hr_employee
        self.env.cr.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'hr_employee' 
            AND column_name = 'default_location_id'
        """)
        has_default_location = bool(self.env.cr.fetchone())

        # Construire la requête en fonction de l'existence de la colonne
        default_location_field = "e.default_location_id" if has_default_location else "NULL"
        
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    a.id as id,
                    CONCAT(e.name, ' - ', to_char(a.check_in, 'YYYY-MM-DD')) as name,
                    a.check_in::date as date,
                    a.employee_id as employee_id,
                    e.department_id as department_id,
                    a.location_id as location_id,
                    %s as default_location_id,
                    a.source as source,
                    a.check_in as check_in,
                    a.check_out as check_out,
                    a.attendance_type_ids as attendance_type_ids,
                    COALESCE(a.working_hours, 0) as working_hours,
                    COALESCE(a.regular_hours, 0) as regular_hours,
                    COALESCE(a.overtime_hours, 0) as overtime_hours,
                    COALESCE(a.late_hours, 0) as late_hours,
                    COALESCE(a.early_leave_hours, 0) as early_leave_hours
                FROM hr_attendance a
                JOIN hr_employee e ON e.id = a.employee_id
            )
        """ % (self._table, default_location_field))

    def _get_records_to_export(self):
        """Retourne les enregistrements à exporter en fonction du contexte"""
        active_ids = self._context.get('active_ids')
        if active_ids:
            # Si des lignes sont sélectionnées, exporter uniquement ces lignes
            return self.browse(active_ids)
        # Sinon, exporter toutes les lignes avec les filtres actuels
        return self.search(self._context.get('search_domain', []))

    def action_export_xlsx(self):
        """Export des rapports de présence au format Excel"""
        records = self._get_records_to_export()

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet('Rapport de présence')

        # Styles
        header_style = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'bg_color': '#D3D3D3',
            'border': 1
        })
        cell_style = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1
        })
        time_style = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'num_format': '[h]:mm'
        })

        # En-têtes
        headers = [
            'Date', 'Employé', 'Département', 'Lieu par défaut', 'Lieu de pointage',
            'Source', 'Entrée', 'Sortie', 'Types de présence', 'Heures travaillées',
            'Heures normales', 'Heures supplémentaires', 'Retard', 'Départ anticipé'
        ]
        for col, header in enumerate(headers):
            worksheet.write(0, col, header, header_style)
            worksheet.set_column(col, col, 15)

        # Données
        row = 1
        for record in records:
            worksheet.write(row, 0, record.date.strftime('%d/%m/%Y'), cell_style)
            worksheet.write(row, 1, record.employee_id.name, cell_style)
            worksheet.write(row, 2, record.department_id.name or '', cell_style)
            worksheet.write(row, 3, record.default_location_id.name or '', cell_style)
            worksheet.write(row, 4, record.location_id.name or '', cell_style)
            worksheet.write(row, 5, dict(self._fields['source'].selection).get(record.source), cell_style)
            worksheet.write(row, 6, record.check_in.strftime('%H:%M') if record.check_in else '', cell_style)
            worksheet.write(row, 7, record.check_out.strftime('%H:%M') if record.check_out else '', cell_style)
            worksheet.write(row, 8, record.attendance_type_ids.replace(',', ', ') if record.attendance_type_ids else '', cell_style)
            worksheet.write(row, 9, record.working_hours, time_style)
            worksheet.write(row, 10, record.regular_hours, time_style)
            worksheet.write(row, 11, record.overtime_hours, time_style)
            worksheet.write(row, 12, record.late_hours, time_style)
            worksheet.write(row, 13, record.early_leave_hours, time_style)
            row += 1

        workbook.close()

        # Création de la pièce jointe
        attachment = self.env['ir.attachment'].create({
            'name': f'Rapport_presence_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx',
            'datas': base64.b64encode(output.getvalue()),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })

        # Retourne l'action pour télécharger le fichier
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    def action_export_pdf(self):
        """Export des rapports de présence au format PDF"""
        records = self._get_records_to_export()
        # Retourne l'action pour générer le PDF
        return self.env.ref('pointeur_hr.action_report_attendance').report_action(records)
