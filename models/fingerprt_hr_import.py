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

class FingerprtHrImport(models.Model):
    _name = 'fingerprt_hr.import'
    _description = 'Import Physical Time Clock Data'
    _order = 'create_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Name', required=True, default=lambda self: self._get_default_name())
    file = fields.Binary(string='File CSV', required=True)
    file_name = fields.Char(string='File Name')
    location_id = fields.Many2one('fingerprt_hr.location', string='Location')
    import_date = fields.Datetime(string='Import Date', readonly=True)
    user_id = fields.Many2one('res.users', string='User', default=lambda self: self.env.user, readonly=True)
    line_count = fields.Integer(string='Number of Lines', compute='_compute_line_count')
    attendance_count = fields.Integer(string='Number of Attendances', compute='_compute_attendance_count')
    notes = fields.Text(string='Notes', tracking=True)
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('imported', 'Imported'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
        ('error', 'Error')
    ], string='State', default='draft', required=True, tracking=True)

    line_ids = fields.One2many('fingerprt_hr.import.line', 'import_id', string='Imported Lines')

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
        """Check that the file is a CSV"""
        for record in self:
            if record.file_name and not record.file_name.lower().endswith('.csv'):
                raise ValidationError(_("Only CSV files are accepted."))

    def _convert_to_float(self, value):
        """Convert a value to float with special case handling"""
        if not value or not isinstance(value, str):
            return 0.0
        
        # Remove spaces and replace comma with dot
        value = value.strip().replace(',', '.')
        
        # Handle negative values
        is_negative = value.startswith('-')
        if is_negative:
            value = value[1:]
        
        try:
            result = float(value)
            return -result if is_negative else result
        except ValueError as e:
            # Log the error for debugging
            _logger.warning(f"Unable to convert '{value}' to float: {str(e)}")
            return 0.0

    def _convert_time_to_float(self, time_str):
        """Convert a time string (HH:MMa/p) to hours"""
        if not time_str:
            return 0.0
        try:
            # Remove spaces
            time_str = time_str.strip()
            
            # Extract am/pm
            is_pm = time_str[-1].lower() == 'p'
            
            # Convert hours and minutes
            hours, minutes = map(int, time_str[:-1].split(':'))
            
            # Adjust for pm
            if is_pm and hours < 12:
                hours += 12
            elif not is_pm and hours == 12:
                hours = 0
                
            return hours + minutes / 60.0
        except Exception:
            return 0.0

    def _convert_to_datetime(self, date_str, time_str):
        """Convert a date (mm/dd/yy) and time (HH:MMa/p) to datetime"""
        
        if not date_str or not time_str:
            _logger.error("Date or time missing")
            return False
            
        try:
            # Convert date
            date = datetime.strptime(date_str, '%m/%d/%y').date()
            
            # Convert time from 12h to 24h
            time_str = time_str.strip()
            if not time_str or len(time_str) < 2:
                _logger.error("Invalid time string")
                return False
                
            # Check AM/PM marker
            am_pm = time_str[-1].lower()
            if am_pm not in ['a', 'p']:
                _logger.error("Invalid AM/PM marker: %s", time_str[-1])
                return False
                
            # Extract hours and minutes
            time_parts = time_str[:-1].split(':')
            if len(time_parts) != 2:
                _logger.error("Invalid time format: %s", time_str)
                return False
                
            hours = int(time_parts[0])
            minutes = int(time_parts[1])
            _logger.info("Time extracted: %d:%02d %s", hours, minutes, am_pm)
            
            # Convert to 24h format
            if am_pm == 'p' and hours < 12:
                hours += 12
            elif am_pm == 'a' and hours == 12:
                hours = 0
                
            _logger.info("Time in 24h format: %d:%02d", hours, minutes)
            
            # Create datetime
            result = datetime.combine(date, time(hours, minutes))
            _logger.info("Final result: %s", result)
            return result
            
        except Exception as e:
            _logger.error("Conversion error: %s", str(e))
            return False

    def _normalize_name(self, name):
        """Normalize a name for comparison"""
        if not name:
            return ""
            
        # Convert to lowercase
        name = name.lower()
        
        # Remove accents
        name = ''.join(c for c in unicodedata.normalize('NFD', name)
                      if unicodedata.category(c) != 'Mn')
        
        # Remove special characters and digits
        name = re.sub(r'[^a-z ]', '', name)
        
        # Remove multiple spaces
        name = re.sub(r'\s+', ' ', name).strip()
        
        # Remove common words and short words
        common_words = ['le', 'la', 'les', 'de', 'du', 'des', 'un', 'une', 'et', 'a', 'au', 'aux']
        words = name.split()
        words = [w for w in words if w not in common_words and len(w) > 1]
        
        return ' '.join(words)

    def _find_employee_by_name(self, employee_name):
        """Find an employee by name using existing mappings or searching in employees"""
        if not employee_name:
            return False
            
        # 1. Search in existing mappings (exact match)
        mapping = self.env['fingerprt_hr.employee.mapping'].search([
            ('name', '=', employee_name),
            ('active', '=', True)
        ], limit=1)
        
        if mapping:
            # Update usage counter
            mapping.write({
                'import_count': mapping.import_count + 1,
                'last_used': fields.Datetime.now()
            })
            return mapping.employee_id
        
        # Normalize the imported name for comparison
        normalized_name = self._normalize_name(employee_name)
        
        # Check if the name is too short or could be just a first name/last name
        words = normalized_name.split()
        
        # If the normalized name is empty or contains a single short word, do not perform automatic matching
        if not normalized_name or (len(words) == 1 and len(normalized_name) < 5):
            _logger.info("Name too short or incomplete for automatic matching: '%s'", employee_name)
            return False
        
        # 2. Search for an employee with the exact name
        employee = self.env['hr.employee'].search([
            ('name', '=', employee_name),
            ('active', '=', True)
        ], limit=1)
        
        if employee:
            # Create a mapping
            try:
                self.env['fingerprt_hr.employee.mapping'].create({
                    'name': employee_name,
                    'employee_id': employee.id,
                    'import_id': self.id
                })
            except Exception as e:
                _logger.error("Error creating mapping: %s", str(e))
            return employee
        
        # 3. Search by similarity if no exact match is found
        # Get all active employees
        all_employees = self.env['hr.employee'].search([('active', '=', True)])
        
        # Prepare normalized employee names
        employee_names = [(emp, self._normalize_name(emp.name)) for emp in all_employees]
        
        best_match = None
        best_score = 0.0
        threshold = 0.85  # Similarity threshold (85%)
        
        for emp, emp_normalized_name in employee_names:
            # Check that the employee name contains at least two words
            emp_words = emp_normalized_name.split()
            if len(emp_words) < 2:
                continue
                
            # Calculate similarity between names
            similarity = difflib.SequenceMatcher(None, normalized_name, emp_normalized_name).ratio()
            
            # Check also if the imported name is contained in the employee name or vice versa
            contains_score = 0
            if normalized_name in emp_normalized_name:
                contains_score = len(normalized_name) / len(emp_normalized_name)
            elif emp_normalized_name in normalized_name:
                contains_score = len(emp_normalized_name) / len(normalized_name)
            
            # Take the best score between similarity and contains score
            final_score = max(similarity, contains_score)
            
            if final_score > best_score:
                best_score = final_score
                best_match = emp
        
        # If a match with a sufficient score is found, create a mapping
        if best_match and best_score >= threshold:
            try:
                self.env['fingerprt_hr.employee.mapping'].create({
                    'name': employee_name,
                    'employee_id': best_match.id,
                    'import_id': self.id,
                    'notes': _("Automatic matching (score: %.2f)") % best_score
                })
                _logger.info("Automatic matching found for '%s': '%s' (score: %.2f)", 
                             employee_name, best_match.name, best_score)
                return best_match
            except Exception as e:
                _logger.error("Error creating matching: %s", str(e))
        
        return False

    def message_post(self, **kwargs):
        """Override to format dates in user's timezone"""
        # Convert date to user's timezone
        user_tz = self.env.user.tz or 'UTC'
        local_tz = pytz.timezone(user_tz)
        utc_now = fields.Datetime.now()
        local_now = pytz.utc.localize(utc_now).astimezone(local_tz)

        # Add local date to message subject
        kwargs['subject'] = kwargs.get('subject', '') + ' - ' + local_now.strftime('%d/%m/%Y %H:%M:%S')
        
        return super(FingerprtHrImport, self).message_post(**kwargs)

    def _import_csv_file(self):
        """Import CSV data"""
        self.ensure_one()
        _logger.info("=== START IMPORT ===")

        if not self.file:
            raise UserError(_("Please select a file to import."))

        # Read CSV file
        csv_data = base64.b64decode(self.file)
        csv_file = io.StringIO(csv_data.decode('utf-8'))
        reader = csv.DictReader(csv_file)
        _logger.info("CSV columns: %s", reader.fieldnames)
        
        success_count = 0
        error_lines = []

        # Delete old lines
        self.line_ids.unlink()

        # Import new lines
        line_vals = []
        for row in reader:
            try:
                # Extract data
                employee_name = row.get('Display Name', '').strip()
                date = row.get('Date', '').strip()
                in_time = row.get('In Time', '').strip()
                out_time = row.get('Out Time', '').strip()

                _logger.info("Processing line: name=%s, date=%s, in=%s, out=%s", 
                           employee_name, date, in_time, out_time)

                # Convert dates and times
                check_in = self._convert_to_datetime(date, in_time) if date and in_time else False
                check_out = self._convert_to_datetime(date, out_time) if date and out_time else False

                _logger.info("Conversion result: check_in=%s, check_out=%s", check_in, check_out)

                # If no check-in, skip the line
                if not check_in:
                    _logger.info("Line ignored: no check-in")
                    continue

                # If check_out is before check_in, add a day
                if check_in and check_out and check_out < check_in:
                    check_out += timedelta(days=1)
                    _logger.info("Adjustment check_out: %s", check_out)

                # Validate required fields
                if not employee_name:
                    raise ValidationError(_("Employee name is required."))
                if not date:
                    raise ValidationError(_("Date is required."))

                # Prepare values
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
                
                _logger.info("Values prepared: %s", vals)

                line_vals.append(vals)
                success_count += 1

            except Exception as e:
                error_message = f"Error line {reader.line_num} ({employee_name if 'employee_name' in locals() else 'unknown'}): {str(e)}"
                error_lines.append(error_message)
                _logger.error(error_message)

        # Create lines
        if line_vals:
            _logger.info("Creating %d lines", len(line_vals))
            self.env['fingerprt_hr.import.line'].create(line_vals)
            
            # Confirmation message with statistics
            message = _("""Import successful on %s :
- %d lines imported
- %d employees different""") % (
                fields.Datetime.now().strftime('%d/%m/%Y à %H:%M:%S'),
                success_count,
                len(set(val['employee_name'] for val in line_vals))
            )
            
            if error_lines:
                message += _("\n\nErrors :\n%s") % '\n'.join(error_lines)
                
            self.message_post(body=message)
            
            return True
        else:
            raise UserError(_("No valid line found in the file."))

    def action_create_attendances(self):
        """Create attendances from imported lines"""
        self.ensure_one()
        
        if self.state not in ['imported']:
            raise UserError(_("You can only create attendances if the import is in the 'Imported' state."))
            
        # Search for matches for lines without employee
        unmapped_lines = self.line_ids.filtered(lambda l: not l.employee_id and l.state != 'done')
        _logger.info("Number of lines without match: %d", len(unmapped_lines))
        mapped_count = 0
        
        for line in unmapped_lines:
            # Search for an employee by name
            if line.employee_name:
                employee = self._find_employee_by_name(line.employee_name)
                if employee:
                    line.write({
                        'employee_id': employee.id,
                        'state': 'mapped'
                    })
                    mapped_count += 1
                    
        # If there are still lines without match, open the selection assistant
        remaining_unmapped = self.line_ids.filtered(lambda l: not l.employee_id and l.state != 'done')
        if remaining_unmapped:
            _logger.info("There are still %d lines without match -> opening selection assistant", len(remaining_unmapped))
            
            # Message for found matches
            if mapped_count > 0:
                self.message_post(
                    body=_("Automatic search for matches :\n- %d lines have been mapped") % mapped_count,
                    message_type='notification',
                    subtype_id=self.env.ref('mail.mt_note').id
                )
            
            return {
                'name': _('Select Employees'),
                'type': 'ir.actions.act_window',
                'res_model': 'fingerprt_hr.select.employees',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'active_id': self.id,
                    'active_model': 'fingerprt_hr.import',
                    'default_mapped_count': mapped_count,
                }
            }
        
        # Otherwise, create attendances directly
        _logger.info("All lines are mapped -> creating attendances")
        if mapped_count > 0:
            self.message_post(
                body=_("Automatic search for matches :\n- %d lines have been mapped") % mapped_count,
                message_type='notification',
                subtype_id=self.env.ref('mail.mt_note').id
            )
        return self._create_attendances(mapped_count)

    def _create_attendances(self, mapped_count=0):
        """Create attendances for lines with an employee"""
        self.ensure_one()
        
        # Create attendances for lines with an employee
        attendance_count = 0
        error_count = 0
        duplicate_count = 0
        
        # Get all mapped lines that don't have an attendance
        mapped_lines = self.line_ids.filtered(lambda l: l.employee_id and l.state in ['mapped'])
        
        for line in mapped_lines:
            try:
                # Verify required data
                if not line.check_in:
                    raise ValidationError(_("Check-in time is required"))
                
                # Check if an attendance already exists for this employee at this date/time
                existing_attendance = self.env['hr.attendance'].search([
                    ('employee_id', '=', line.employee_id.id),
                    ('check_in', '=', line.check_in),
                    ('location_id', '=', line.location_id.id if line.location_id else False)
                ], limit=1)
                
                if existing_attendance:
                    # Mark as duplicate and pass to next line
                    line.write({
                        'attendance_id': existing_attendance.id,
                        'state': 'done',
                        'notes': _("Attendance already exists and associated")
                    })
                    duplicate_count += 1
                    continue
                
                # Create attendance
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
                
                # Update the line
                line.write({
                    'attendance_id': attendance.id,
                    'state': 'done'
                })
                attendance_count += 1
                
            except Exception as e:
                error_message = str(e)
                line.write({
                    'state': 'error',
                    'notes': _("Error while creating attendance: %s") % error_message
                })
                error_count += 1
                
        # Update import state if at least one attendance was created
        if attendance_count > 0 or duplicate_count > 0:
            self.write({'state': 'done'})
            
        # Confirmation message
        unmapped_count = len(self.line_ids.filtered(lambda l: not l.employee_id))
        error_count = len(self.line_ids.filtered(lambda l: l.state == 'error'))
        
        message = _("""
Creation of attendances completed :
- %d attendances created
- %d duplicates detected and associated
- %d lines without match
- %d lines in error
""") % (attendance_count, duplicate_count, unmapped_count, error_count)

        self.message_post(body=message)
        
        return True

    def action_view_attendances(self):
        """View created attendances"""
        self.ensure_one()
        
        attendances = self.env['hr.attendance'].search([
            ('import_id', '=', self.id)
        ])
        
        return {
            'name': _('Attendances'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.attendance',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', attendances.ids)],
        }
        
    def action_search_employee_mappings(self):
        """Search for employee mappings for lines without employee"""
        self.ensure_one()
        _logger.info("=== BEGIN SEARCHING FOR MATCHING EMPLOYEES ===")
        
        # Get lines without employee
        unmapped_lines = self.line_ids.filtered(lambda l: not l.employee_id and l.state != 'done')
        
        if not unmapped_lines:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'message': _("All lines already have an employee associated."),
                    'type': 'info',
                }
            }
            
        # Search for existing mappings
        for line in unmapped_lines:
            _logger.info("Searching for matching employee: %s", line.employee_name)
            mapping = self.env['fingerprt_hr.employee.mapping'].search([
                ('name', '=', line.employee_name),
                ('active', '=', True)
            ], limit=1)
            
            if mapping:
                try:
                    _logger.info("Matching found: %s -> %s",
                               mapping.name, mapping.employee_id.name)
                    line.write({
                        'employee_id': mapping.employee_id.id,
                        'state': 'mapped'
                    })
                    # Update usage counter
                    mapping.write({
                        'import_count': mapping.import_count + 1,
                        'last_used': fields.Datetime.now()
                    })
                except Exception as e:
                    _logger.error("Error updating line: %s", str(e))
                    
        # Count remaining lines without match
        remaining = len(self.line_ids.filtered(lambda l: not l.employee_id and l.state != 'done'))
        
        # Prepare return message
        if remaining == 0:
            message = _("All matches have been found.")
            msg_type = 'success'
        else:
            message = _(
                "%d line(s) remain(s) without match. "
                "Use the selection wizard to manually associate them."
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
        """View associated mappings for this import"""
        self.ensure_one()
        
        # Retrieve all mappings associated with this import
        mappings = self.env['fingerprt_hr.employee.mapping'].search([
            ('import_id', '=', self.id)
        ])
        
        action = {
            'name': _('Mappings'),
            'type': 'ir.actions.act_window',
            'res_model': 'fingerprt_hr.employee.mapping',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', mappings.ids)],
            'context': {'default_import_id': self.id},
            'target': 'current',
        }
        
        # If one mapping, open the form directly
        if len(mappings) == 1:
            action['res_id'] = mappings.id
            action['view_mode'] = 'form'
            
        return action

    def action_view_attendances(self):
        """View created attendances for this import"""
        self.ensure_one()
        
        # Retrieve all attendances associated with this import
        attendances = self.line_ids.mapped('attendance_id')
        
        # Create action to display attendances
        action = {
            'name': _('Attendances'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.attendance',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', attendances.ids)],
            'context': {'create': False},  # Prevent manual creation
            'target': 'current',
        }
        
        # If one attendance, open the form directly
        if len(attendances) == 1:
            action['res_id'] = attendances.id
            action['view_mode'] = 'form'
            
        return action

    def action_cancel(self):
        """Cancel the import"""
        for record in self:
            if record.state == 'done':
                raise UserError(_("Impossible d'annuler un import terminé."))
            record.write({'state': 'cancelled'})
            
    def action_reset(self):
        """Reset the import"""
        for record in self:
            # Delete attendances if they exist
            attendances = record.line_ids.mapped('attendance_id')
            if attendances:
                attendances.unlink()
            
            # Reset lines
            record.line_ids.write({
                'state': 'imported',
                'error_message': False,
                'notes': False,
                'employee_id': False,
                'attendance_id': False
            })
            
            # Reset import
            record.write({
                'state': 'imported',
                'import_date': fields.Datetime.now()
            })

    def _get_default_name(self):
        """Get a default name with the current date and time in the user's timezone"""
        user = self.env.user
        if user.tz:
            user_tz = pytz.timezone(user.tz)
        else:
            user_tz = pytz.UTC
            
        # Get the current date and time in the user's timezone
        now_utc = datetime.now(pytz.UTC)
        now_user_tz = now_utc.astimezone(user_tz)
        
        return _('Import %s') % now_user_tz.strftime('%d/%m/%Y à %H:%M')

    def action_import_file(self):
        """Import the CSV file"""
        self.ensure_one()
        if not self.file:
            raise UserError(_("Please select a file to import."))
            
        if self.state != 'draft':
            raise UserError(_("You can only import if the state is 'Draft'."))
            
        # Update state
        self.write({
            'state': 'imported',
            'import_date': fields.Datetime.now()
        })
            
        # Import the file
        try:
            self._import_csv_file()
            # Generate initial mapping report
            self._generate_mapping_report()
            return True
        except Exception as e:
            self.state = 'error'
            self.message_post(body=_("Erreur lors de l'import : %s") % str(e))
            raise UserError(_("Erreur lors de l'import : %s") % str(e))

    def _name_similarity_score(self, name1, name2):
        """Calculate similarity score between two names"""
        if not name1 or not name2:
            return 0.0
            
        # Normalize the names
        normalized_name1 = self._normalize_name(name1)
        normalized_name2 = self._normalize_name(name2)
        
        if not normalized_name1 or not normalized_name2:
            return 0.0
            
        # If the name is too short or could be just a first name/last name, return 0
        if len(normalized_name1.split()) == 1 and len(normalized_name1) < 5:
            return 0.0
            
        if len(normalized_name2.split()) == 1 and len(normalized_name2) < 5:
            return 0.0
            
        # Calculate similarity
        similarity = difflib.SequenceMatcher(None, normalized_name1, normalized_name2).ratio()
        
        # Check if one name is contained in the other
        contains_score = 0.0
        if normalized_name1 in normalized_name2:
            contains_score = len(normalized_name1) / len(normalized_name2)
        elif normalized_name2 in normalized_name1:
            contains_score = len(normalized_name2) / len(normalized_name1)
            
        # Return the best score
        return max(similarity, contains_score)

    def _generate_mapping_report(self):
        """Generate a report on the mappings"""
        # Statistics on the mappings
        total_lines = len(self.line_ids)
        mapped_lines = len(self.line_ids.filtered(lambda l: l.employee_id))
        unmapped_lines = total_lines - mapped_lines
        
        # Retrieve names without match
        unmapped_names = self.line_ids.filtered(lambda l: not l.employee_id).mapped('employee_name')
        
        # Find similar names to suggest mappings
        suggestions = []
        for name in unmapped_names[:10]:  # Limit to 10 names to avoid a long report
            if not name:  # Ignore empty names
                continue
                
            # Check if the name is too short for suggestions
            normalized_name = self._normalize_name(name)
            if not normalized_name or (len(normalized_name.split()) == 1 and len(normalized_name) < 5):
                continue
                
            employees = self.env['hr.employee'].search([('active', '=', True)], limit=10)
            matches = []
            
            for employee in employees:
                if not employee.name:  # Ignore employees without name
                    continue
                    
                score = self._name_similarity_score(name, employee.name)
                if score >= 0.3:  # Low threshold for suggestions
                    matches.append((employee, score))
            
            matches.sort(key=lambda x: x[1], reverse=True)
            if matches:
                suggestions.append((name, matches[:3]))  # Keep the 3 best suggestions
        
        # Generate the report
        report = _("""
<h3>Mapping Report</h3>
<p>
<strong>Statistics :</strong><br/>
- Lines imported : {total}<br/>
- Lines with match : {mapped} ({mapped_percent:.1f}%)<br/>
- Lines without match : {unmapped} ({unmapped_percent:.1f}%)
</p>
""").format(
            total=total_lines,
            mapped=mapped_lines,
            unmapped=unmapped_lines,
            mapped_percent=(mapped_lines/total_lines*100) if total_lines else 0,
            unmapped_percent=(unmapped_lines/total_lines*100) if total_lines else 0
        )
        
        # Add suggestions if available
        if suggestions:
            report += _("<h4>Matching suggestions :</h4><ul>")
            for name, matches in suggestions:
                report += _("<li><strong>{}</strong> : ").format(name)
                for employee, score in matches:
                    report += _("{} (score: {:.2f}), ").format(employee.name, score)
                report = report[:-2] + "</li>"  # Remove the last comma
            report += "</ul>"
        
        return report

    def action_mapping_report(self):
        """Action to generate and display the mapping report"""
        self.ensure_one()
        report = self._generate_mapping_report()
        self.message_post(body=report)
