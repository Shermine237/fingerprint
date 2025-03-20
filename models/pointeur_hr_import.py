from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import base64
import csv
import io
import logging
import re
from datetime import datetime, timedelta, time
import pytz
import difflib
import unicodedata

_logger = logging.getLogger(__name__)

class PointeurHrImport(models.Model):
    _name = 'pointeur_hr.import'
    _description = 'Import des données du pointeur physique'
    _order = 'create_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Nom', required=True, default=lambda self: self._get_default_name())
    file = fields.Binary(string='Fichier CSV', required=True)
    file_name = fields.Char(string='Nom du fichier')
    location_id = fields.Many2one('pointeur_hr.location', string='Lieu de pointage')
    import_date = fields.Datetime(string='Date d\'import', readonly=True)
    user_id = fields.Many2one('res.users', string='Utilisateur', default=lambda self: self.env.user, readonly=True)
    line_count = fields.Integer(string='Nombre de lignes', compute='_compute_line_count')
    attendance_count = fields.Integer(string='Nombre de présences', compute='_compute_attendance_count')
    notes = fields.Text(string='Notes', tracking=True)
    
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('imported', 'Données importées'),
        ('done', 'Présences créées'),
        ('cancelled', 'Annulé'),
        ('error', 'Erreur')
    ], string='État', default='draft', required=True, tracking=True)

    line_ids = fields.One2many('pointeur_hr.import.line', 'import_id', string='Lignes importées')

    @api.depends('line_ids')
    def _compute_line_count(self):
        for record in self:
            record.line_count = len(record.line_ids)

    @api.depends('line_ids.attendance_id')
    def _compute_attendance_count(self):
        for record in self:
            record.attendance_count = len(record.line_ids.filtered(lambda l: l.attendance_id))

    @api.constrains('file_name')
    def _check_file_extension(self):
        """Vérifier que le fichier est un CSV"""
        for record in self:
            if record.file_name and not record.file_name.lower().endswith('.csv'):
                raise ValidationError(_("Seuls les fichiers CSV sont acceptés."))

    def _convert_to_float(self, value):
        """Convertir une valeur en float avec gestion des cas particuliers"""
        if not value or not isinstance(value, str):
            return 0.0
        
        # Supprimer les espaces et remplacer la virgule par un point
        value = value.strip().replace(',', '.')
        
        # Gérer les valeurs négatives
        is_negative = value.startswith('-')
        if is_negative:
            value = value[1:]
        
        try:
            result = float(value)
            return -result if is_negative else result
        except ValueError as e:
            # Log l'erreur pour le débogage
            _logger.warning(f"Impossible de convertir '{value}' en float: {str(e)}")
            return 0.0

    def _convert_time_to_float(self, time_str):
        """Convertit une chaîne de temps (HH:MMa/p) en nombre d'heures"""
        if not time_str:
            return 0.0
        try:
            # Suppression des espaces
            time_str = time_str.strip()
            
            # Extraction de am/pm
            is_pm = time_str[-1].lower() == 'p'
            
            # Conversion en heures et minutes
            hours, minutes = map(int, time_str[:-1].split(':'))
            
            # Ajustement pour pm
            if is_pm and hours < 12:
                hours += 12
            elif not is_pm and hours == 12:
                hours = 0
                
            return hours + minutes / 60.0
        except Exception:
            return 0.0

    def _convert_to_datetime(self, date_str, time_str):
        """Convertit une date (mm/dd/yy) et une heure (HH:MMa/p) en datetime"""
        _logger.info("=== DÉBUT CONVERSION DATE/HEURE ===")
        _logger.info("Entrée : date=%s, heure=%s", date_str, time_str)
        
        if not date_str or not time_str:
            _logger.error("Date ou heure manquante")
            return False
            
        try:
            # Conversion de la date
            date = datetime.strptime(date_str, '%m/%d/%y').date()
            _logger.info("Date convertie : %s", date)
            
            # Conversion de l'heure au format 12h en 24h
            time_str = time_str.strip()
            if not time_str or len(time_str) < 2:
                _logger.error("Chaîne d'heure invalide")
                return False
                
            # Vérification du marqueur AM/PM
            am_pm = time_str[-1].lower()
            if am_pm not in ['a', 'p']:
                _logger.error("Marqueur AM/PM invalide : %s", time_str[-1])
                return False
                
            # Extraction des heures et minutes
            time_parts = time_str[:-1].split(':')
            if len(time_parts) != 2:
                _logger.error("Format d'heure invalide : %s", time_str)
                return False
                
            hours = int(time_parts[0])
            minutes = int(time_parts[1])
            _logger.info("Heure extraite : %d:%02d %s", hours, minutes, am_pm)
            
            # Conversion en format 24h
            if am_pm == 'p' and hours < 12:
                hours += 12
            elif am_pm == 'a' and hours == 12:
                hours = 0
                
            _logger.info("Heure 24h : %d:%02d", hours, minutes)
            
            # Création du datetime
            result = datetime.combine(date, time(hours, minutes))
            _logger.info("Résultat final : %s", result)
            return result
            
        except Exception as e:
            _logger.error("Erreur de conversion : %s", str(e))
            return False

    def _normalize_name(self, name):
        """Normalise un nom pour la comparaison"""
        if not name:
            return ""
            
        # Convertir en minuscules
        name = name.lower()
        
        # Supprimer les accents
        name = ''.join(c for c in unicodedata.normalize('NFD', name)
                      if unicodedata.category(c) != 'Mn')
        
        # Supprimer les caractères spéciaux et les chiffres
        name = re.sub(r'[^a-z ]', '', name)
        
        # Supprimer les espaces multiples
        name = re.sub(r'\s+', ' ', name).strip()
        
        # Supprimer les mots courts et communs (articles, prépositions)
        common_words = ['le', 'la', 'les', 'de', 'du', 'des', 'un', 'une', 'et', 'a', 'au', 'aux']
        words = name.split()
        words = [w for w in words if w not in common_words and len(w) > 1]
        
        return ' '.join(words)

    def _find_employee_by_name(self, employee_name):
        """Recherche un employé par son nom en utilisant les correspondances existantes ou en recherchant dans les employés"""
        if not employee_name:
            return False
            
        # 1. Rechercher dans les correspondances existantes (correspondance exacte)
        mapping = self.env['pointeur_hr.employee.mapping'].search([
            ('name', '=', employee_name),
            ('active', '=', True)
        ], limit=1)
        
        if mapping:
            # Mettre à jour le compteur d'utilisation
            mapping.write({
                'import_count': mapping.import_count + 1,
                'last_used': fields.Datetime.now()
            })
            return mapping.employee_id
        
        # Normaliser le nom importé pour la comparaison
        normalized_name = self._normalize_name(employee_name)
        
        # Vérifier si le nom est trop court ou pourrait être juste un prénom/nom
        words = normalized_name.split()
        
        # Si le nom normalisé est vide ou contient un seul mot court, ne pas faire de correspondance automatique
        if not normalized_name or (len(words) == 1 and len(normalized_name) < 5):
            _logger.info("Nom trop court ou incomplet pour correspondance automatique: '%s'", employee_name)
            return False
        
        # 2. Rechercher un employé avec le nom exact
        employee = self.env['hr.employee'].search([
            ('name', '=', employee_name),
            ('active', '=', True)
        ], limit=1)
        
        if employee:
            # Créer une correspondance
            try:
                self.env['pointeur_hr.employee.mapping'].create({
                    'name': employee_name,
                    'employee_id': employee.id,
                    'import_id': self.id
                })
            except Exception as e:
                _logger.error("Erreur création correspondance : %s", str(e))
            return employee
        
        # 3. Recherche par similarité si aucune correspondance exacte n'est trouvée
        # Récupérer tous les employés actifs
        all_employees = self.env['hr.employee'].search([('active', '=', True)])
        
        # Préparer les noms normalisés des employés
        employee_names = [(emp, self._normalize_name(emp.name)) for emp in all_employees]
        
        best_match = None
        best_score = 0.0
        threshold = 0.85  # Seuil de similarité (85%)
        
        for emp, emp_normalized_name in employee_names:
            # Vérifier que le nom de l'employé contient au moins deux mots
            emp_words = emp_normalized_name.split()
            if len(emp_words) < 2:
                continue
                
            # Calculer la similarité entre les noms
            similarity = difflib.SequenceMatcher(None, normalized_name, emp_normalized_name).ratio()
            
            # Vérifier également si le nom importé est contenu dans le nom de l'employé ou vice versa
            contains_score = 0
            if normalized_name in emp_normalized_name:
                contains_score = len(normalized_name) / len(emp_normalized_name)
            elif emp_normalized_name in normalized_name:
                contains_score = len(emp_normalized_name) / len(normalized_name)
            
            # Prendre le meilleur score entre la similarité et le score de contenance
            final_score = max(similarity, contains_score)
            
            if final_score > best_score:
                best_score = final_score
                best_match = emp
        
        # Si un match avec un score suffisant est trouvé, créer une correspondance
        if best_match and best_score >= threshold:
            try:
                self.env['pointeur_hr.employee.mapping'].create({
                    'name': employee_name,
                    'employee_id': best_match.id,
                    'import_id': self.id,
                    'notes': _("Correspondance automatique (score: %.2f)") % best_score
                })
                _logger.info("Correspondance trouvée pour '%s': '%s' (score: %.2f)", 
                             employee_name, best_match.name, best_score)
                return best_match
            except Exception as e:
                _logger.error("Erreur création correspondance : %s", str(e))
        
        return False

    def message_post(self, **kwargs):
        """Surcharge pour formater les dates dans le fuseau horaire de l'utilisateur"""
        # Conversion de la date dans le fuseau horaire de l'utilisateur
        user_tz = self.env.user.tz or 'UTC'
        local_tz = pytz.timezone(user_tz)
        utc_now = fields.Datetime.now()
        local_now = pytz.utc.localize(utc_now).astimezone(local_tz)

        # Ajout de la date locale dans le message
        kwargs['subject'] = kwargs.get('subject', '') + ' - ' + local_now.strftime('%d/%m/%Y %H:%M:%S')
        
        return super(PointeurHrImport, self).message_post(**kwargs)

    def _import_csv_file(self):
        """Importer les données du fichier CSV"""
        self.ensure_one()
        _logger.info("=== DÉBUT IMPORT ===")

        if not self.file:
            raise UserError(_("Veuillez sélectionner un fichier à importer."))

        # Lecture du fichier CSV
        csv_data = base64.b64decode(self.file)
        csv_file = io.StringIO(csv_data.decode('utf-8'))
        reader = csv.DictReader(csv_file)
        _logger.info("Colonnes CSV : %s", reader.fieldnames)
        
        success_count = 0
        error_lines = []

        # Suppression des anciennes lignes
        self.line_ids.unlink()

        # Import des nouvelles lignes
        line_vals = []
        for row in reader:
            try:
                # Extraction des données
                employee_name = row.get('Display Name', '').strip()
                date = row.get('Date', '').strip()
                in_time = row.get('In Time', '').strip()
                out_time = row.get('Out Time', '').strip()

                _logger.info("Traitement ligne : name=%s, date=%s, in=%s, out=%s", 
                           employee_name, date, in_time, out_time)

                # Construction des dates et heures
                check_in = self._convert_to_datetime(date, in_time) if date and in_time else False
                check_out = self._convert_to_datetime(date, out_time) if date and out_time else False

                _logger.info("Résultat conversion : check_in=%s, check_out=%s", check_in, check_out)

                # Si pas de check-in, on ignore la ligne
                if not check_in:
                    _logger.info("Ligne ignorée : pas de check-in")
                    continue

                # Si check_out est avant check_in, on ajoute un jour
                if check_in and check_out and check_out < check_in:
                    check_out += timedelta(days=1)
                    _logger.info("Ajustement check_out : %s", check_out)

                # Validation des données obligatoires
                if not employee_name:
                    raise ValidationError(_("Le nom de l'employé est obligatoire."))
                if not date:
                    raise ValidationError(_("La date est obligatoire."))

                # Préparation des valeurs
                vals = {
                    'import_id': self.id,
                    'employee_name': employee_name,
                    'display_id': row.get('Display ID', '').strip(),
                    'payroll_id': row.get('Payroll ID', '').strip(),
                    'department': row.get('Department', '').strip(),
                    'dept_code': row.get('Dept. Code', '').strip(),
                    'date': datetime.strptime(date, '%m/%d/%y').date() if date else False,
                    'check_in': check_in,
                    'check_out': check_out,
                    'in_note': row.get('In Note', '').strip(),
                    'out_note': row.get('Out Note', '').strip(),
                    'reg_hours': float(row.get('REG', '0') or '0'),
                    'ot1_hours': float(row.get('OT1', '0') or '0'),
                    'ot2_hours': float(row.get('OT2', '0') or '0'),
                    'total_hours': float(row.get('Total', '0') or '0'),
                    'location_id': self.location_id.id if self.location_id else False,
                    'state': 'imported'
                }
                
                _logger.info("Valeurs préparées : %s", vals)

                line_vals.append(vals)
                success_count += 1

            except Exception as e:
                error_message = f"Erreur ligne {reader.line_num} ({employee_name if 'employee_name' in locals() else 'inconnu'}): {str(e)}"
                error_lines.append(error_message)
                _logger.error(error_message)

        # Création des lignes
        if line_vals:
            _logger.info("Création de %d lignes", len(line_vals))
            self.env['pointeur_hr.import.line'].create(line_vals)
            
            # Message de confirmation avec statistiques
            message = _("""Import réussi le %s :
- %d lignes importées
- %d employés différents""") % (
                fields.Datetime.now().strftime('%d/%m/%Y à %H:%M:%S'),
                success_count,
                len(set(val['employee_name'] for val in line_vals))
            )
            
            if error_lines:
                message += _("\n\nErreurs :\n%s") % '\n'.join(error_lines)
                
            self.message_post(body=message)
            
            return True
        else:
            raise UserError(_("Aucune ligne valide trouvée dans le fichier."))

    def action_create_attendances(self):
        """Créer les présences à partir des lignes importées"""
        self.ensure_one()
        
        if self.state not in ['imported']:
            raise UserError(_("Vous ne pouvez créer les présences que si l'import est à l'état 'Importé'."))
            
        # Recherche des correspondances pour les lignes sans employé
        unmapped_lines = self.line_ids.filtered(lambda l: not l.employee_id and l.state != 'done')
        _logger.info("Nombre de lignes sans correspondance : %d", len(unmapped_lines))
        mapped_count = 0
        
        for line in unmapped_lines:
            # Recherche d'un employé par son nom
            if line.employee_name:
                employee = self._find_employee_by_name(line.employee_name)
                if employee:
                    line.write({
                        'employee_id': employee.id,
                        'state': 'mapped'
                    })
                    mapped_count += 1
                    
        # S'il reste des lignes sans correspondance, ouvrir l'assistant de sélection
        remaining_unmapped = self.line_ids.filtered(lambda l: not l.employee_id and l.state != 'done')
        if remaining_unmapped:
            _logger.info("Il reste %d lignes non mappées -> ouverture assistant", len(remaining_unmapped))
            
            # Message pour les correspondances trouvées
            if mapped_count > 0:
                self.message_post(
                    body=_("Recherche automatique des correspondances :\n- %d lignes ont été mappées") % mapped_count,
                    message_type='notification',
                    subtype_id=self.env.ref('mail.mt_note').id
                )
            
            return {
                'name': _('Sélectionner les employés'),
                'type': 'ir.actions.act_window',
                'res_model': 'pointeur_hr.select.employees',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'active_id': self.id,
                    'active_model': 'pointeur_hr.import',
                    'default_mapped_count': mapped_count,
                }
            }
        
        # Sinon, créer directement les présences
        _logger.info("Toutes les lignes sont mappées -> création des présences")
        if mapped_count > 0:
            self.message_post(
                body=_("Recherche automatique des correspondances :\n- %d lignes ont été mappées") % mapped_count,
                message_type='notification',
                subtype_id=self.env.ref('mail.mt_note').id
            )
        return self._create_attendances(mapped_count)

    def _create_attendances(self, mapped_count=0):
        """Créer les présences pour les lignes avec un employé"""
        self.ensure_one()
        
        # Création des présences pour les lignes avec un employé
        attendance_count = 0
        error_count = 0
        duplicate_count = 0
        
        # Récupérer toutes les lignes mappées qui n'ont pas encore de présence
        mapped_lines = self.line_ids.filtered(lambda l: l.employee_id and l.state in ['mapped'])
        
        for line in mapped_lines:
            try:
                # Vérifier les données obligatoires
                if not line.check_in:
                    raise ValidationError(_("L'heure d'entrée est obligatoire"))
                
                # Vérifier si une présence existe déjà pour cet employé à cette date/heure
                existing_attendance = self.env['hr.attendance'].search([
                    ('employee_id', '=', line.employee_id.id),
                    ('check_in', '=', line.check_in),
                    ('location_id', '=', line.location_id.id if line.location_id else False)
                ], limit=1)
                
                if existing_attendance:
                    # Marquer comme doublon et passer à la ligne suivante
                    line.write({
                        'attendance_id': existing_attendance.id,
                        'state': 'done',
                        'notes': _("Présence existante détectée et associée")
                    })
                    duplicate_count += 1
                    continue
                
                # Créer la présence
                attendance_vals = {
                    'employee_id': line.employee_id.id,
                    'check_in': line.check_in,
                    'check_out': line.check_out,
                    'location_id': line.location_id.id if line.location_id else False,
                    'source': 'import',
                    'import_id': self.id,
                    'import_line_id': line.id
                }
                
                attendance = self.env['hr.attendance'].create(attendance_vals)
                
                # Mettre à jour la ligne
                line.write({
                    'attendance_id': attendance.id,
                    'state': 'done'
                })
                attendance_count += 1
                
            except Exception as e:
                error_message = str(e)
                line.write({
                    'state': 'error',
                    'notes': _("Erreur lors de la création de la présence : %s") % error_message
                })
                error_count += 1
                
        # Mise à jour de l'état de l'import si au moins une présence a été créée
        if attendance_count > 0 or duplicate_count > 0:
            self.write({'state': 'done'})
            
        # Message de confirmation
        unmapped_count = len(self.line_ids.filtered(lambda l: not l.employee_id))
        error_count = len(self.line_ids.filtered(lambda l: l.state == 'error'))
        
        message = _("""
Création des présences terminée :
- %d présences créées
- %d doublons détectés et associés
- %d lignes sans correspondance
- %d lignes en erreur
""") % (attendance_count, duplicate_count, unmapped_count, error_count)

        self.message_post(body=message)
        
        return True

    def action_view_attendances(self):
        """Voir les présences créées"""
        self.ensure_one()
        
        attendances = self.env['hr.attendance'].search([
            ('import_id', '=', self.id)
        ])
        
        return {
            'name': _('Présences'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.attendance',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', attendances.ids)],
        }
        
    def action_search_employee_mappings(self):
        """Rechercher les correspondances pour les lignes sans employé"""
        self.ensure_one()
        _logger.info("=== DÉBUT RECHERCHE CORRESPONDANCES ===")
        
        # Récupérer les lignes sans employé
        unmapped_lines = self.line_ids.filtered(lambda l: not l.employee_id and l.state != 'done')
        
        if not unmapped_lines:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': _("Toutes les lignes ont déjà un employé associé."),
                    'type': 'info',
                }
            }
            
        # Rechercher les correspondances existantes
        for line in unmapped_lines:
            _logger.info("Recherche correspondance pour : %s", line.employee_name)
            mapping = self.env['pointeur_hr.employee.mapping'].search([
                ('name', '=', line.employee_name),
                ('active', '=', True)
            ], limit=1)
            
            if mapping:
                try:
                    _logger.info("Correspondance trouvée : %s -> %s", 
                               mapping.name, mapping.employee_id.name)
                    line.write({
                        'employee_id': mapping.employee_id.id,
                        'state': 'mapped'
                    })
                    # Mettre à jour le compteur d'utilisation
                    mapping.write({
                        'import_count': mapping.import_count + 1,
                        'last_used': fields.Datetime.now()
                    })
                except Exception as e:
                    _logger.error("Erreur mise à jour ligne : %s", str(e))
                    
        # Compter les lignes restantes sans correspondance
        remaining = len(self.line_ids.filtered(lambda l: not l.employee_id and l.state != 'done'))
        
        # Préparer le message de retour
        if remaining == 0:
            message = _("Toutes les correspondances ont été trouvées.")
            msg_type = 'success'
        else:
            message = _(
                "%d ligne(s) reste(nt) sans correspondance. "
                "Utilisez le wizard de sélection pour les associer manuellement."
            ) % remaining
            msg_type = 'warning'
            
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': message,
                'type': msg_type,
                'sticky': True
            }
        }

    def action_view_mappings(self):
        """Voir les correspondances associées à cet import"""
        self.ensure_one()
        
        # Récupérer toutes les correspondances liées à cet import
        mappings = self.env['pointeur_hr.employee.mapping'].search([
            ('import_id', '=', self.id)
        ])
        
        action = {
            'name': _('Correspondances'),
            'type': 'ir.actions.act_window',
            'res_model': 'pointeur_hr.employee.mapping',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', mappings.ids)],
            'context': {'default_import_id': self.id},
            'target': 'current',
        }
        
        # Si une seule correspondance, ouvrir directement le formulaire
        if len(mappings) == 1:
            action['res_id'] = mappings.id
            action['view_mode'] = 'form'
            
        return action

    def action_view_attendances(self):
        """Voir les présences créées pour cet import"""
        self.ensure_one()
        
        # Récupérer toutes les présences liées à cet import
        attendances = self.line_ids.mapped('attendance_id')
        
        # Créer l'action pour afficher les présences
        action = {
            'name': _('Présences'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.attendance',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', attendances.ids)],
            'context': {'create': False},  # Empêcher la création manuelle
            'target': 'current',
        }
        
        # Si une seule présence, ouvrir directement le formulaire
        if len(attendances) == 1:
            action['res_id'] = attendances.id
            action['view_mode'] = 'form'
            
        return action

    def action_cancel(self):
        """Annuler l'import"""
        for record in self:
            if record.state == 'done':
                raise UserError(_("Impossible d'annuler un import terminé."))
            record.write({'state': 'cancelled'})
            
    def action_reset(self):
        """Réinitialiser l'import"""
        for record in self:
            # Supprimer les présences si elles existent
            attendances = record.line_ids.mapped('attendance_id')
            if attendances:
                attendances.unlink()
            
            # Réinitialiser les lignes
            record.line_ids.write({
                'state': 'imported',
                'error_message': False,
                'notes': False,
                'employee_id': False,
                'attendance_id': False
            })
            
            # Réinitialiser l'import
            record.write({
                'state': 'imported',
                'import_date': fields.Datetime.now()
            })

    def _get_default_name(self):
        """Obtenir un nom par défaut avec la date et l'heure actuelles dans le fuseau horaire de l'utilisateur"""
        user = self.env.user
        if user.tz:
            user_tz = pytz.timezone(user.tz)
        else:
            user_tz = pytz.UTC
            
        # Obtenir la date et l'heure actuelles dans le fuseau horaire de l'utilisateur
        now_utc = datetime.now(pytz.UTC)
        now_user_tz = now_utc.astimezone(user_tz)
        
        return _('Import du %s') % now_user_tz.strftime('%d/%m/%Y à %H:%M')

    def action_import_file(self):
        """Importer le fichier CSV"""
        self.ensure_one()
        if not self.file:
            raise UserError(_("Veuillez sélectionner un fichier à importer."))
            
        if self.state != 'draft':
            raise UserError(_("Vous ne pouvez importer que si l'état est 'Brouillon'."))
            
        # Mise à jour de l'état
        self.write({
            'state': 'imported',
            'import_date': fields.Datetime.now()
        })
            
        # Import du fichier
        try:
            self._import_csv_file()
            # Générer un rapport de correspondance initial
            self._generate_mapping_report()
            return True
        except Exception as e:
            self.state = 'error'
            self.message_post(body=_("Erreur lors de l'import : %s") % str(e))
            raise UserError(_("Erreur lors de l'import : %s") % str(e))

    def _generate_mapping_report(self):
        """Génère un rapport sur l'état des correspondances"""
        if not self.line_ids:
            return
            
        # Statistiques sur les correspondances
        total_lines = len(self.line_ids)
        mapped_lines = len(self.line_ids.filtered(lambda l: l.employee_id))
        unmapped_lines = total_lines - mapped_lines
        
        # Récupérer les noms sans correspondance
        unmapped_names = self.line_ids.filtered(lambda l: not l.employee_id).mapped('employee_name')
        
        # Trouver les noms similaires pour suggérer des correspondances
        suggestions = []
        for name in unmapped_names[:10]:  # Limiter aux 10 premiers pour éviter un rapport trop long
            employees = self.env['hr.employee'].search([], limit=3)
            matches = []
            for employee in employees:
                score = self._name_similarity_score(name, employee.name)
                if score >= 0.3:  # Seuil bas pour avoir des suggestions
                    matches.append((employee, score))
            
            matches.sort(key=lambda x: x[1], reverse=True)
            if matches:
                suggestions.append((name, matches[:3]))  # Garder les 3 meilleures suggestions
        
        # Générer le rapport
        report = _("""
<h3>Rapport de correspondance</h3>
<p>
<strong>Statistiques :</strong><br/>
- Lignes importées : {total}<br/>
- Lignes avec correspondance : {mapped} ({mapped_percent:.1f}%)<br/>
- Lignes sans correspondance : {unmapped} ({unmapped_percent:.1f}%)
</p>
""").format(
            total=total_lines,
            mapped=mapped_lines,
            unmapped=unmapped_lines,
            mapped_percent=(mapped_lines/total_lines*100) if total_lines else 0,
            unmapped_percent=(unmapped_lines/total_lines*100) if total_lines else 0
        )
        
        # Ajouter les suggestions si disponibles
        if suggestions:
            report += _("<h4>Suggestions de correspondance :</h4><ul>")
            for name, matches in suggestions:
                report += _("<li><strong>{}</strong> : ").format(name)
                for employee, score in matches:
                    report += _("{} (score: {:.2f}), ").format(employee.name, score)
                report = report[:-2] + "</li>"  # Enlever la dernière virgule
            report += "</ul>"
        
        self.message_post(body=report)
        return True

    def action_search_employee_mappings(self):
        """Rechercher les correspondances pour les lignes sans employé"""
        self.ensure_one()
        _logger.info("=== DÉBUT RECHERCHE CORRESPONDANCES ===")
        
        # Récupérer les lignes sans employé
        unmapped_lines = self.line_ids.filtered(lambda l: not l.employee_id and l.state != 'done')
        
        if not unmapped_lines:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': _("Toutes les lignes ont déjà un employé associé."),
                    'type': 'info',
                }
            }
            
        # Rechercher les correspondances existantes
        for line in unmapped_lines:
            _logger.info("Recherche correspondance pour : %s", line.employee_name)
            mapping = self.env['pointeur_hr.employee.mapping'].search([
                ('name', '=', line.employee_name),
                ('active', '=', True)
            ], limit=1)
            
            if mapping:
                try:
                    _logger.info("Correspondance trouvée : %s -> %s", 
                               mapping.name, mapping.employee_id.name)
                    line.write({
                        'employee_id': mapping.employee_id.id,
                        'state': 'mapped'
                    })
                    # Mettre à jour le compteur d'utilisation
                    mapping.write({
                        'import_count': mapping.import_count + 1,
                        'last_used': fields.Datetime.now()
                    })
                except Exception as e:
                    _logger.error("Erreur mise à jour ligne : %s", str(e))
                    
        # Compter les lignes restantes sans correspondance
        remaining = len(self.line_ids.filtered(lambda l: not l.employee_id and l.state != 'done'))
        
        # Préparer le message de retour
        if remaining == 0:
            message = _("Toutes les correspondances ont été trouvées.")
            msg_type = 'success'
        else:
            message = _(
                "%d ligne(s) reste(nt) sans correspondance. "
                "Utilisez le wizard de sélection pour les associer manuellement."
            ) % remaining
            msg_type = 'warning'
            
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': message,
                'type': msg_type,
                'sticky': True
            }
        }

    def action_view_mappings(self):
        """Voir les correspondances associées à cet import"""
        self.ensure_one()
        
        # Récupérer toutes les correspondances liées à cet import
        mappings = self.env['pointeur_hr.employee.mapping'].search([
            ('import_id', '=', self.id)
        ])
        
        action = {
            'name': _('Correspondances'),
            'type': 'ir.actions.act_window',
            'res_model': 'pointeur_hr.employee.mapping',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', mappings.ids)],
            'context': {'default_import_id': self.id},
            'target': 'current',
        }
        
        # Si une seule correspondance, ouvrir directement le formulaire
        if len(mappings) == 1:
            action['res_id'] = mappings.id
            action['view_mode'] = 'form'
            
        return action

    def action_view_attendances(self):
        """Voir les présences créées pour cet import"""
        self.ensure_one()
        
        # Récupérer toutes les présences liées à cet import
        attendances = self.line_ids.mapped('attendance_id')
        
        # Créer l'action pour afficher les présences
        action = {
            'name': _('Présences'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.attendance',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', attendances.ids)],
            'context': {'create': False},  # Empêcher la création manuelle
            'target': 'current',
        }
        
        # Si une seule présence, ouvrir directement le formulaire
        if len(attendances) == 1:
            action['res_id'] = attendances.id
            action['view_mode'] = 'form'
            
        return action

    def action_cancel(self):
        """Annuler l'import"""
        for record in self:
            if record.state == 'done':
                raise UserError(_("Impossible d'annuler un import terminé."))
            record.write({'state': 'cancelled'})
            
    def action_reset(self):
        """Réinitialiser l'import"""
        for record in self:
            # Supprimer les présences si elles existent
            attendances = record.line_ids.mapped('attendance_id')
            if attendances:
                attendances.unlink()
            
            # Réinitialiser les lignes
            record.line_ids.write({
                'state': 'imported',
                'error_message': False,
                'notes': False,
                'employee_id': False,
                'attendance_id': False
            })
            
            # Réinitialiser l'import
            record.write({
                'state': 'imported',
                'import_date': fields.Datetime.now()
            })

    def _get_default_name(self):
        """Obtenir un nom par défaut avec la date et l'heure actuelles dans le fuseau horaire de l'utilisateur"""
        user = self.env.user
        if user.tz:
            user_tz = pytz.timezone(user.tz)
        else:
            user_tz = pytz.UTC
            
        # Obtenir la date et l'heure actuelles dans le fuseau horaire de l'utilisateur
        now_utc = datetime.now(pytz.UTC)
        now_user_tz = now_utc.astimezone(user_tz)
        
        return _('Import du %s') % now_user_tz.strftime('%d/%m/%Y à %H:%M')
