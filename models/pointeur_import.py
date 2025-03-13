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

    def action_import(self):
        """Importer les données du fichier CSV"""
        self.ensure_one()

        if not self.file:
            raise UserError(_("Veuillez sélectionner un fichier à importer."))

        # Lecture du fichier CSV
        csv_data = base64.b64decode(self.file)
        csv_file = io.StringIO(csv_data.decode('utf-8'))
        reader = csv.DictReader(csv_file)
        success_count = 0
        error_lines = []

        # Suppression des anciennes lignes
        self.line_ids.unlink()

        # Affichage des en-têtes pour le débogage
        headers = reader.fieldnames
        self.message_post(body=_("En-têtes du fichier CSV:\n%s") % ', '.join(headers))

        line_vals = []
        for row in reader:
            try:
                # Extraction des données
                check_in_date = datetime.strptime(row['Date'], '%m/%d/%y').date()
                check_in_time = row.get('In Time', '').strip()
                check_out_time = row.get('Out Time', '').strip()

                # Construction des dates et heures
                check_in = self._convert_to_datetime(check_in_date, check_in_time) if check_in_time else False
                check_out = self._convert_to_datetime(check_in_date, check_out_time) if check_out_time else False

                # Préparation des valeurs
                vals = {
                    'import_id': self.id,
                    'employee_name': row.get('Display Name', '').strip(),
                    'display_id': row.get('Display ID', '').strip(),
                    'department': row.get('Department', '').strip(),
                    'dept_code': row.get('Dept. Code', '').strip(),
                    'payroll_id': row.get('Payroll ID', '').strip(),
                    'date': check_in_date,
                    'check_in_date': check_in_date,
                    'check_in_time': check_in_time,
                    'check_out_date': check_in_date,  # Par défaut même jour
                    'check_out_time': check_out_time,
                    'check_in': check_in,
                    'check_out': check_out,
                    'in_note': row.get('In Note', '').strip(),
                    'out_note': row.get('Out Note', '').strip(),
                    'reg_hours': self._convert_to_float(row.get('Reg. Hours', '0')),
                    'ot1_hours': self._convert_to_float(row.get('OT1 Hours', '0')),
                    'ot2_hours': self._convert_to_float(row.get('OT2 Hours', '0')),
                    'total_hours': self._convert_to_float(row.get('Total Hours', '0')),
                    'state': 'imported'
                }

                line_vals.append(vals)

            except Exception as e:
                error_lines.append(f"Erreur ligne {reader.line_num}: {str(e)}")

        # Création des lignes
        if line_vals:
            self.env['pointeur_hr.import.line'].create(line_vals)
            self.state = 'imported'
            self.import_date = fields.Datetime.now()

        # Mise à jour du statut et des messages
        if error_lines:
            self.message_post(body=_("Erreurs d'importation:\n%s") % '\n'.join(error_lines))
            self.state = 'error'
        else:
            message = _("%d lignes ont été importées avec succès.") % len(line_vals)
            self.message_post(body=message)

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

    def action_create_attendances(self):
        """Création des présences à partir des lignes importées"""
        self.ensure_one()
        
        # On vérifie que toutes les lignes sont en état 'imported'
        if any(line.state != 'imported' for line in self.line_ids):
            raise UserError(_("Toutes les lignes doivent être en état 'Importé' avant de créer les présences"))
            
        attendances = self.env['hr.attendance']
        success_count = 0
        error_count = 0
        
        # Statistiques des correspondances
        perfect_matches = 0
        partial_matches = 0
        no_matches = 0
        
        for line in self.line_ids:
            try:
                # Recherche de l'employé par son nom
                employee = self._find_employee_by_name(line.employee_name)
                if not employee:
                    no_matches += 1
                    raise ValidationError(_("Impossible de trouver l'employé avec le nom : %s") % line.employee_name)
                elif self._name_similarity_score(line.employee_name, employee.name) == 1:
                    perfect_matches += 1
                else:
                    partial_matches += 1
                    
                # Création de la présence
                attendance = attendances.create({
                    'employee_id': employee.id,
                    'check_in': line.check_in,
                    'check_out': line.check_out,
                    'location_id': line.location_id.id if line.location_id else False,
                })
                
                # Mise à jour de la ligne
                line.write({
                    'state': 'done',
                    'attendance_id': attendance.id,
                })
                success_count += 1
                
            except Exception as e:
                error_count += 1
                # En cas d'erreur, on met à jour la ligne avec l'erreur
                line.write({
                    'state': 'error',
                    'error_message': str(e),
                })
                
        # Log des statistiques
        _logger.info("Import des présences terminé : %d succès, %d erreurs", success_count, error_count)
        _logger.info("Statistiques des correspondances : %d parfaites, %d partielles, %d non trouvées", 
                    perfect_matches, partial_matches, no_matches)
                
        # Mise à jour du statut de l'import avec statistiques détaillées
        if all(line.state == 'done' for line in self.line_ids):
            self.state = 'done'
            message = _("""Import terminé avec succès :
- %d présences créées
- %d correspondances parfaites
- %d correspondances partielles""") % (success_count, perfect_matches, partial_matches)
            self.message_post(body=message)
        elif any(line.state == 'error' for line in self.line_ids):
            self.state = 'error'
            message = _("""Import terminé avec des erreurs :
- %d présences créées
- %d erreurs
- %d correspondances parfaites
- %d correspondances partielles
- %d employés non trouvés""") % (success_count, error_count, perfect_matches, partial_matches, no_matches)
            self.message_post(body=message)

    def _convert_to_datetime(self, date, time):
        """Convertir une date et une heure en datetime"""
        if not date or not time:
            return False
        
        try:
            return datetime.strptime(f"{date} {time}", '%Y-%m-%d %H:%M')
        except ValueError as e:
            raise ValueError(f"Erreur de format pour la date et l'heure. Format attendu: 'YYYY-MM-DD HH:MM', reçu: '{date} {time}'. Erreur: {str(e)}")

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
