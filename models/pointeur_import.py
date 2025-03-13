from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import base64
import csv
import io
import logging
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)

class PointeurImport(models.Model):
    _name = 'pointeur_hr.import'
    _description = 'Import des données du pointeur physique'
    _order = 'create_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Nom', required=True, default=lambda self: _('Import du %s') % fields.Date.context_today(self).strftime('%d/%m/%Y'))
    file = fields.Binary(string='Fichier CSV', required=True)
    file_name = fields.Char(string='Nom du fichier')
    location_id = fields.Many2one('pointeur_hr.location', string='Lieu de pointage')
    import_date = fields.Datetime(string='Date d\'import', readonly=True)
    user_id = fields.Many2one('res.users', string='Utilisateur', default=lambda self: self.env.user, readonly=True)
    line_count = fields.Integer(string='Nombre de lignes', compute='_compute_line_count')
    attendance_count = fields.Integer(string='Nombre de présences', compute='_compute_attendance_count')
    
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
        if not date_str or not time_str:
            _logger.warning("Date ou heure manquante : date=%s, heure=%s", date_str, time_str)
            return False
            
        try:
            # Log pour le débogage
            _logger.info("Conversion date/heure : date='%s' heure='%s'", date_str, time_str)
            
            # Conversion de la date
            try:
                date = datetime.strptime(date_str, '%m/%d/%y').date()
                _logger.info("Date convertie : %s", date)
            except ValueError as e:
                _logger.error("Erreur conversion date '%s': %s", date_str, str(e))
                return False
            
            # Suppression des espaces et vérification du format
            time_str = time_str.strip()
            if not time_str[-1].lower() in ['a', 'p']:
                _logger.error("Format d'heure invalide (pas de a/p) : %s", time_str)
                return False
            
            # Extraction de am/pm
            is_pm = time_str[-1].lower() == 'p'
            time_str = time_str[:-1].strip()  # Supprime le a/p
            
            # Conversion en heures et minutes
            try:
                if ':' in time_str:
                    hours, minutes = map(int, time_str.split(':'))
                else:
                    _logger.error("Format d'heure invalide (pas de :) : %s", time_str)
                    return False
                    
                _logger.info("Heures extraites : %d:%02d %s", hours, minutes, 'PM' if is_pm else 'AM')
                
                # Validation des heures et minutes
                if not (0 <= hours <= 12 and 0 <= minutes <= 59):
                    _logger.error("Heures ou minutes invalides : %d:%02d", hours, minutes)
                    return False
                
                # Ajustement pour pm
                if is_pm and hours < 12:
                    hours += 12
                elif not is_pm and hours == 12:
                    hours = 0
                    
                _logger.info("Heures après ajustement AM/PM : %d:%02d", hours, minutes)
                
            except ValueError as e:
                _logger.error("Erreur conversion heure '%s': %s", time_str, str(e))
                return False
                
            # Création du datetime
            try:
                result = datetime.combine(date, datetime.time(hours, minutes))
                _logger.info("Datetime final : %s", result)
                return result
            except ValueError as e:
                _logger.error("Erreur création datetime : %s", str(e))
                return False
            
        except Exception as e:
            _logger.error("Erreur lors de la conversion de la date/heure : %s, %s - %s", date_str, time_str, str(e))
            return False

    def _normalize_name(self, name):
        """Normalise un nom pour la comparaison
        - Convertit en minuscules
        - Supprime les espaces en début/fin
        - Supprime les espaces multiples
        - Gère les initiales"""
        if not name:
            return ''
            
        # Conversion en minuscules et suppression des espaces
        name = name.lower().strip()
        
        # Suppression des espaces multiples
        name = ' '.join(name.split())
        
        return name

    def _get_initials(self, name):
        """Extrait les initiales d'un nom"""
        if not name:
            return ''
        
        # Découpage en mots
        words = name.split()
        
        # Extraction des initiales
        initials = ''.join(word[0] for word in words if word)
        
        return initials.lower()

    def _name_similarity_score(self, name1, name2):
        """Calcule un score de similarité entre deux noms
        - Score de 0 à 1, 1 étant une correspondance parfaite
        - Prend en compte :
          * Les mots exacts
          * Les mots partiels (min 3 caractères)
          * Les initiales
          * Les noms composés"""
        if not name1 or not name2:
            return 0
            
        # Normalisation des noms
        name1 = self._normalize_name(name1)
        name2 = self._normalize_name(name2)
        
        # Si les noms sont identiques après normalisation
        if name1 == name2:
            return 1
            
        # Découpage en mots
        words1 = name1.split()
        words2 = name2.split()
        
        # Score basé sur les mots communs
        common_words = set(words1).intersection(set(words2))
        if not common_words:
            # Si aucun mot commun, on vérifie les initiales
            initials1 = self._get_initials(name1)
            initials2 = self._get_initials(name2)
            if initials1 and initials2 and initials1 == initials2:
                return 0.6
            return 0
            
        # Score de base sur les mots exacts
        exact_score = len(common_words) / max(len(words1), len(words2))
        
        # Score pour les mots partiels et composés
        partial_matches = 0
        for w1 in words1:
            for w2 in words2:
                # Si un mot est contenu dans l'autre (minimum 3 caractères)
                if w1 != w2 and (w1 in w2 or w2 in w1) and len(min(w1, w2, key=len)) >= 3:
                    partial_matches += 0.5
                # Si les 3 premiers caractères sont identiques
                elif len(w1) >= 3 and len(w2) >= 3 and w1[:3] == w2[:3]:
                    partial_matches += 0.3
                # Si c'est un nom composé (avec tiret ou espace)
                elif ('-' in w1 or '-' in w2) and any(part in w2 for part in w1.split('-')) or any(part in w1 for part in w2.split('-')):
                    partial_matches += 0.4
                    
        partial_score = partial_matches / max(len(words1), len(words2))
        
        # Score final combiné
        return min(1.0, exact_score + partial_score)

    def _find_employee_by_name(self, name):
        """Trouve un employé par son nom de manière intelligente.
        Gère les variations dans l'écriture des noms :
        - Majuscules/minuscules
        - Espaces
        - Initiales
        - Noms composés
        - Ordres des mots"""
        if not name:
            return False
            
        # Recherche de tous les employés
        employees = self.env['hr.employee'].search([])
        best_match = False
        best_score = 0
        matches = []
        
        # Log pour le débogage
        _logger.info("Recherche de correspondance pour le nom : %s", name)
        
        for employee in employees:
            # Calcul du score de similarité
            score = self._name_similarity_score(name, employee.name)
            
            # Log des scores pour le débogage
            if score > 0:
                _logger.info("Score de correspondance : %.2f entre '%s' et '%s'", score, name, employee.name)
                matches.append((employee, score))
            
            # Si le score est meilleur que le précédent
            if score > best_score:
                best_score = score
                best_match = employee
                _logger.info("Nouveau meilleur score : %.2f avec l'employé '%s'", score, employee.name)
                
            # Si correspondance parfaite, on arrête là
            if score == 1:
                _logger.info("Correspondance parfaite trouvée avec l'employé '%s'", employee.name)
                return employee
                
        # Log du résultat final
        if best_match and best_score >= 0.5:
            _logger.info("Meilleure correspondance trouvée : '%s' (score : %.2f)", best_match.name, best_score)
        else:
            _logger.warning("Aucune correspondance trouvée pour le nom : '%s' (meilleur score : %.2f)", name, best_score)
            
        # Affichage des correspondances dans l'interface
        if matches:
            matches.sort(key=lambda x: x[1], reverse=True)
            message = _("Correspondances trouvées pour '%s' :\n") % name
            for employee, score in matches[:5]:  # On affiche les 5 meilleures correspondances
                message += _("- %s (score : %.2f)\n") % (employee.name, score)
            self.message_post(body=message)
        
        # On retourne le meilleur match si son score est suffisant
        return best_match if best_score >= 0.5 else False

    def action_import(self):
        """Importer les données du fichier CSV"""
        self.ensure_one()

        if not self.file:
            raise UserError(_("Veuillez sélectionner un fichier à importer."))

        # Lecture du fichier CSV
        csv_data = base64.b64decode(self.file)
        
        # Aperçu du contenu du fichier
        preview = self._preview_csv_content(csv_data)
        _logger.info("Aperçu du fichier CSV :\n%s", preview)
        
        csv_file = io.StringIO(csv_data.decode('utf-8'))
        reader = csv.DictReader(csv_file)
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

                # Log pour le débogage
                _logger.info("Traitement ligne %d : employé='%s', date='%s', entrée='%s', sortie='%s'", 
                           reader.line_num, employee_name, date, in_time, out_time)

                # Construction des dates et heures
                check_in = self._convert_to_datetime(date, in_time) if in_time else False
                check_out = self._convert_to_datetime(date, out_time) if out_time else False

                # Log des résultats de conversion
                _logger.info("Après conversion ligne %d : check_in=%s, check_out=%s", 
                           reader.line_num, check_in, check_out)

                # Si check_out est avant check_in, on ajoute un jour
                if check_in and check_out and check_out < check_in:
                    check_out += timedelta(days=1)
                    _logger.info("Ajustement check_out après minuit : %s", check_out)

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

                line_vals.append(vals)
                success_count += 1

            except Exception as e:
                error_message = f"Erreur ligne {reader.line_num} ({employee_name}): {str(e)}"
                error_lines.append(error_message)
                _logger.error(error_message)

        # Création des lignes
        if line_vals:
            self.env['pointeur_hr.import.line'].create(line_vals)
            self.state = 'imported'
            self.import_date = fields.Datetime.now()
            
            # Message de confirmation avec statistiques
            message = _("""Import réussi :
- %d lignes importées
- %d employés différents""") % (
                success_count,
                len(set(val['employee_name'] for val in line_vals))
            )
            
            if error_lines:
                message += _("\n\nErreurs :\n%s") % '\n'.join(error_lines)
                self.state = 'error'
                
            self.message_post(body=message)

    def action_create_attendances(self):
        """Créer les présences à partir des lignes importées"""
        self.ensure_one()

        if self.state != 'imported':
            raise UserError(_("Vous devez d'abord importer les données du fichier CSV."))

        # Création des présences
        for line in self.line_ids.filtered(lambda l: l.state == 'imported'):
            try:
                # Recherche de l'employé
                employee = self.env['hr.employee'].search([
                    '|',
                    ('name', '=', line.employee_name),
                    ('badge_id', '=', line.display_id)
                ], limit=1)

                if not employee:
                    raise ValidationError(_("Employé non trouvé : %s") % line.employee_name)

                # Création de la présence
                attendance = self.env['hr.attendance'].create({
                    'employee_id': employee.id,
                    'check_in': line.check_in,
                    'check_out': line.check_out,
                    'location_id': line.location_id.id if line.location_id else False,
                    'source': 'import'
                })

                # Mise à jour de la ligne
                line.write({
                    'attendance_id': attendance.id,
                    'state': 'done'
                })

            except Exception as e:
                line.write({
                    'state': 'error',
                    'error_message': str(e)
                })

        # Mise à jour de l'état de l'import
        if all(line.state == 'done' for line in self.line_ids):
            self.state = 'done'
        elif any(line.state == 'error' for line in self.line_ids):
            self.state = 'error'

        # Message de confirmation
        message = _("""Création des présences terminée :
- %d présences créées
- %d erreurs""") % (
            len(self.line_ids.filtered(lambda l: l.state == 'done')),
            len(self.line_ids.filtered(lambda l: l.state == 'error'))
        )
        self.message_post(body=message)

    def action_view_attendances(self):
        """Voir les présences créées"""
        self.ensure_one()
        attendances = self.line_ids.mapped('attendance_id')
        action = {
            'name': _('Présences'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.attendance',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', attendances.ids)],
        }
        return action

    def action_cancel(self):
        """Annuler l'import"""
        self.ensure_one()
        self.state = 'cancelled'

    def action_reset(self):
        """Réinitialiser l'import"""
        self.ensure_one()
        self.state = 'draft'
        self.line_ids.unlink()
