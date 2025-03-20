# Attendance Manager HR

## Description
This module extends the standard Odoo 14 attendance module by adding advanced features for importing and managing employee attendance data from external files.

## Main Features

### 1. Attendance Data Import
- CSV file import for attendance data
- Support for different date and time formats
- Normal and overtime hours management
- Bulk attendance import
- Data validation and verification

### 2. Employee Mapping System
- Intelligent mapping system between imported names and Odoo employees
- Employee selection wizard for manual mapping
- Protection against multiple mappings (one employee = one name)
- Active/inactive mapping management
- Automatic reactivation of inactive mappings when needed

### 3. Attendance Processing
- Automatic attendance creation from imported data
- Check-in and check-out time validation
- Location association
- Line status management (imported, mapped, done, error)
- Error line reset capability

### 4. Advanced User Interface
- Tree view of import lines with status color coding
- Custom search filters
- Contextual line actions
- Clear temporary notifications
- Real-time import statistics

## Detailed User Guide

### 1. Data Import
1. Access "Attendance > Imports" menu
2. Click "Create" to start a new import
3. Select your CSV file
4. Choose default location (optional)
5. Click "Import" to load data

### 2. Mapping Management
#### Automatic Mapping
1. After import, click "Search Mappings"
2. The system will attempt to automatically match imported names with existing employees
3. Successfully mapped lines will change to "mapped" status

#### Manual Mapping
1. For unmapped lines, use the employee selection wizard
2. Select the correct employee for each name
3. Choose whether to create permanent mappings
4. Confirm selections to create mappings

### 3. Attendance Creation
1. Once mapping is complete, click "Create Attendances"
2. The system will:
   - Validate check-in/out times
   - Create attendance records
   - Associate locations
   - Update line statuses

### 4. Error Management
1. Lines with errors will be marked in red
2. View error details in the line form
3. Fix issues and reset lines
4. Retry attendance creation

## Technical Information

### Dependencies
- base
- hr_attendance
- hr

### Module Structure
- models/: Data models
- views/: XML views
- security/: Access rights
- reports/: Report templates
- wizards/: Import wizards
- data/: Configuration data

### Key Features
- Location-based attendance tracking
- Attendance data import
- Attendance reports
- Normal and overtime hours tracking
- Import error management

## Installation

1. Copy module to your Odoo addons directory
2. Update modules list
3. Install "fingerprint HR" module

## Configuration

1. Set up employee access rights
2. Configure default locations
3. Set up attendance policies
4. Configure import settings

## Support

For support and bug reports, please create an issue in the repository or contact the module maintainer.

## License

This module is licensed under LGPL-3.

## Author

Developed by Charlie Rostant YOSSA
