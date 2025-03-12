from odoo import api, fields, models, _
from odoo.exceptions import UserError
import base64
import csv
import io
import logging
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)

class PointeurImport(models.Model):
    _name = 'pointeur.import'
    _description = 'Import des données du pointeur physique'
    _order = 'create_date desc'

    name = fields.Char(string='Nom', required=True, default=lambda self: _('Import du %s') % fields.Date.context_today(self).strftime('%d/%m/%Y'))
    file = fields.Binary(string='Fichier CSV', required=True)
    filename = fields.Char(string='Nom du fichier')
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('imported', 'Importé'),
        ('done', 'Terminé'),
        ('cancelled', 'Annulé')
    ], string='État', default='draft')
    import_date = fields.Datetime(string='Date d\'import')
    user_id = fields.Many2one('res.users', string='Utilisateur', default=lambda self: self.env.user)
    line_ids = fields.One2many('pointeur.import.line', 'import_id', string='Lignes')
    line_count = fields.Integer(string='Nombre de lignes', compute='_compute_line_count')
    attendance_count = fields.Integer(string='Présences créées', compute='_compute_attendance_count')
    
    @api.depends('line_ids')
    def _compute_line_count(self):
        for record in self:
            record.line_count = len(record.line_ids)
    
    @api.depends('line_ids.attendance_id')
    def _compute_attendance_count(self):
        for record in self:
            record.attendance_count = len(record.line_ids.filtered(lambda l: l.attendance_id))
    
    def action_import(self):
        self.ensure_one()
        if not self.file:
            raise UserError(_('Veuillez sélectionner un fichier à importer.'))
        
        # Supprimer les lignes existantes
        self.line_ids.unlink()
        
        # Lire le fichier CSV
        csv_data = base64.b64decode(self.file)
        csv_file = io.StringIO(csv_data.decode('utf-8'))
        reader = csv.reader(csv_file)
        
        # Ignorer la ligne d'en-tête
        headers = next(reader)
        
        # Créer les lignes d'import
        for row in reader:
            if len(row) < 8:  # Vérifier que la ligne a au moins les colonnes nécessaires
                continue
                
            display_name = row[0]
            display_id = row[1]
            payroll_id = row[2]
            date_str = row[3]
            in_day = row[4]
            in_time = row[5]
            out_day = row[6]
            out_time = row[7]
            department = row[8] if len(row) > 8 else ''
            dept_code = row[9] if len(row) > 9 else ''
            
            # Convertir les dates et heures
            try:
                date_obj = datetime.strptime(date_str, '%m/%d/%y')
                
                # Convertir l'heure d'entrée
                if in_time:
                    # Format: 06:44a ou 06:44p
                    hour, minute_ampm = in_time[:-1].split(':')
                    minute = minute_ampm[:2]
                    ampm = in_time[-1]
                    
                    hour = int(hour)
                    if ampm.lower() == 'p' and hour < 12:
                        hour += 12
                    elif ampm.lower() == 'a' and hour == 12:
                        hour = 0
                    
                    check_in = date_obj.replace(hour=hour, minute=int(minute))
                else:
                    check_in = False
                
                # Convertir l'heure de sortie
                if out_time:
                    # Format: 09:30p ou 09:30a
                    hour, minute_ampm = out_time[:-1].split(':')
                    minute = minute_ampm[:2]
                    ampm = out_time[-1]
                    
                    hour = int(hour)
                    if ampm.lower() == 'p' and hour < 12:
                        hour += 12
                    elif ampm.lower() == 'a' and hour == 12:
                        hour = 0
                    
                    # Gérer le cas où la sortie est le jour suivant
                    out_date_obj = date_obj
                    if in_day != out_day:
                        # Déterminer le nombre de jours à ajouter
                        days_of_week = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
                        in_day_idx = days_of_week.index(in_day)
                        out_day_idx = days_of_week.index(out_day)
                        
                        days_diff = out_day_idx - in_day_idx
                        if days_diff <= 0:
                            days_diff += 7
                        
                        out_date_obj = date_obj + timedelta(days=days_diff)
                    
                    check_out = out_date_obj.replace(hour=hour, minute=int(minute))
                else:
                    check_out = False
                
                # Calculer les heures travaillées
                reg_hours = float(row[12]) if len(row) > 12 and row[12] else 0.0
                ot1_hours = float(row[13]) if len(row) > 13 and row[13] else 0.0
                ot2_hours = float(row[14]) if len(row) > 14 and row[14] else 0.0
                total_hours = float(row[19]) if len(row) > 19 and row[19] else 0.0
                
                # Créer la ligne d'import
                self.env['pointeur.import.line'].create({
                    'import_id': self.id,
                    'display_name': display_name,
                    'display_id': display_id,
                    'payroll_id': payroll_id,
                    'date': date_obj,
                    'check_in': check_in,
                    'check_out': check_out,
                    'department': department,
                    'dept_code': dept_code,
                    'reg_hours': reg_hours,
                    'ot1_hours': ot1_hours,
                    'ot2_hours': ot2_hours,
                    'total_hours': total_hours,
                })
                
            except Exception as e:
                _logger.error('Erreur lors de l\'import de la ligne %s: %s', row, e)
                continue
        
        self.write({
            'state': 'imported',
            'import_date': fields.Datetime.now(),
        })
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Lignes importées'),
            'res_model': 'pointeur.import.line',
            'view_mode': 'tree,form',
            'domain': [('import_id', '=', self.id)],
            'context': {'default_import_id': self.id},
        }
    
    def action_create_attendances(self):
        self.ensure_one()
        if self.state != 'imported':
            raise UserError(_('Vous devez d\'abord importer les données.'))
        
        for line in self.line_ids.filtered(lambda l: not l.attendance_id and l.check_in and l.check_out):
            # Rechercher l'employé par son ID de pointage
            employee = self.env['hr.employee'].search([('barcode', '=', line.display_id)], limit=1)
            if not employee:
                # Essayer de trouver par nom
                employee = self.env['hr.employee'].search([('name', 'ilike', line.display_name)], limit=1)
            
            if not employee:
                line.state = 'error'
                line.note = _('Employé non trouvé')
                continue
            
            # Rechercher le département
            department = False
            if line.department:
                department = self.env['hr.department'].search([('name', 'ilike', line.department)], limit=1)
                if not department and line.dept_code:
                    department = self.env['hr.department'].search([('code', '=', line.dept_code)], limit=1)
            
            # Déterminer le type de présence
            attendance_type = 'normal'
            if line.ot1_hours > 0 or line.ot2_hours > 0:
                attendance_type = 'overtime'
            
            # Calculer les heures supplémentaires
            overtime_hours = line.ot1_hours + line.ot2_hours
            
            # Créer la présence
            try:
                attendance = self.env['hr.attendance'].create({
                    'employee_id': employee.id,
                    'check_in': line.check_in,
                    'check_out': line.check_out,
                    'department_id': department.id if department else employee.department_id.id,
                    'attendance_type': attendance_type,
                    'overtime_hours': overtime_hours,
                    'working_hours': line.reg_hours,
                })
                
                line.write({
                    'attendance_id': attendance.id,
                    'state': 'done',
                    'note': _('Présence créée avec succès'),
                })
                
            except Exception as e:
                line.state = 'error'
                line.note = _('Erreur lors de la création de la présence: %s') % str(e)
        
        self.write({'state': 'done'})
        
        return True
    
    def action_cancel(self):
        self.ensure_one()
        self.write({'state': 'cancelled'})
        return True
    
    def action_reset(self):
        self.ensure_one()
        self.write({'state': 'draft'})
        return True
    
    def action_view_attendances(self):
        self.ensure_one()
        attendances = self.line_ids.mapped('attendance_id')
        action = self.env.ref('hr_attendance.hr_attendance_action').read()[0]
        if len(attendances) > 1:
            action['domain'] = [('id', 'in', attendances.ids)]
        elif len(attendances) == 1:
            action['views'] = [(self.env.ref('hr_attendance.hr_attendance_view_form').id, 'form')]
            action['res_id'] = attendances.id
        else:
            action = {'type': 'ir.actions.act_window_close'}
        return action


class PointeurImportLine(models.Model):
    _name = 'pointeur.import.line'
    _description = 'Ligne d\'import du pointeur'
    _order = 'date desc, display_name'

    import_id = fields.Many2one('pointeur.import', string='Import', required=True, ondelete='cascade')
    display_name = fields.Char(string='Nom affiché', required=True)
    display_id = fields.Char(string='ID affiché', required=True)
    payroll_id = fields.Char(string='ID de paie')
    date = fields.Date(string='Date', required=True)
    check_in = fields.Datetime(string='Entrée')
    check_out = fields.Datetime(string='Sortie')
    department = fields.Char(string='Département')
    dept_code = fields.Char(string='Code département')
    reg_hours = fields.Float(string='Heures régulières')
    ot1_hours = fields.Float(string='Heures supp. 1')
    ot2_hours = fields.Float(string='Heures supp. 2')
    total_hours = fields.Float(string='Total heures')
    attendance_id = fields.Many2one('hr.attendance', string='Présence')
    state = fields.Selection([
        ('pending', 'En attente'),
        ('done', 'Terminé'),
        ('error', 'Erreur')
    ], string='État', default='pending')
    note = fields.Text(string='Note')
    
    def action_view_attendance(self):
        self.ensure_one()
        if not self.attendance_id:
            raise UserError(_('Aucune présence associée à cette ligne.'))
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Présence'),
            'res_model': 'hr.attendance',
            'view_mode': 'form',
            'res_id': self.attendance_id.id,
        }
