# Pointeur HR

## Description
Ce module étend les fonctionnalités du module de présences standard d'Odoo 14 en ajoutant des fonctionnalités avancées pour l'importation et la gestion des pointages d'employés à partir de fichiers externes.

## Fonctionnalités principales

### 1. Import des données de pointage
- Import de fichiers CSV contenant les données de pointage
- Support de différents formats de date et heure
- Gestion des heures normales et supplémentaires
- Import en masse des pointages
- Validation et vérification des données importées

### 2. Gestion des correspondances employés
- Système intelligent de correspondance entre noms importés et employés Odoo
- Assistant de sélection des employés pour les correspondances manuelles
- Protection contre les correspondances multiples (un employé = un seul nom)
- Gestion des correspondances actives/inactives
- Réactivation automatique des correspondances inactives si nécessaire

### 3. Traitement des présences
- Création automatique des présences à partir des données importées
- Validation des heures d'entrée et de sortie
- Association avec les lieux de pointage
- Gestion des états des lignes (importé, mappé, terminé, erreur)
- Possibilité de réinitialiser les lignes en erreur

### 4. Interface utilisateur avancée
- Vue arborescente des lignes d'import avec code couleur selon l'état
- Filtres de recherche personnalisés
- Actions contextuelles sur les lignes
- Notifications temporaires et claires
- Statistiques en temps réel sur l'import

## Guide utilisateur détaillé

### 1. Import des données
1. Accédez au menu "Présences > Imports"
2. Cliquez sur "Créer" pour démarrer un nouvel import
3. Sélectionnez votre fichier CSV
4. Choisissez le lieu de pointage par défaut (optionnel)
5. Cliquez sur "Importer" pour charger les données

### 2. Gestion des correspondances
#### Correspondance automatique
1. Une fois l'import effectué, cliquez sur "Rechercher correspondances"
2. Le système tentera de faire correspondre automatiquement les noms importés avec les employés existants
3. Les lignes avec correspondance passeront à l'état "mapped"

#### Correspondance manuelle
1. Sélectionnez les lignes sans correspondance
2. Cliquez sur "Attribuer employés"
3. Dans l'assistant :
   - Sélectionnez l'employé correspondant pour chaque nom
   - Cochez/décochez "Créer correspondance" selon vos besoins
   - Le système empêche d'attribuer un employé à plusieurs noms différents
4. Validez pour créer les correspondances

### 3. Création des présences
1. Une fois les correspondances établies, cliquez sur "Créer présences"
2. Le système :
   - Vérifie la validité des données
   - Crée les présences pour les lignes valides
   - Marque les lignes comme "terminées"
   - Signale les erreurs éventuelles

### 4. Gestion des erreurs
1. Les lignes en erreur sont marquées en rouge
2. Pour chaque ligne en erreur :
   - Consultez le message d'erreur détaillé
   - Corrigez les données si nécessaire
   - Utilisez "Réinitialiser" pour retenter le traitement

### 5. Suivi et statistiques
- Consultez les statistiques de l'import en temps réel
- Utilisez les filtres pour analyser les données
- Accédez aux présences créées via le bouton "Voir présences"
- Consultez les correspondances via "Voir correspondances"

### 6. Gestion des correspondances employés
1. Accédez au menu "Présences > Configuration > Correspondances employés"
2. Consultez toutes les correspondances existantes
3. Activez/désactivez les correspondances selon vos besoins
4. Suivez les statistiques d'utilisation de chaque correspondance

### 7. Configuration des lieux de pointage
1. Accédez au menu "Présences > Configuration > Lieux de pointage"
2. Créez et gérez vos différents lieux de pointage
3. Associez des lieux par défaut aux employés si nécessaire

## Configuration

### Prérequis
- Module hr (Ressources Humaines)
- Module hr_attendance (Présences)

### Installation
1. Copiez ce module dans le dossier des addons d'Odoo
2. Mettez à jour la liste des modules
3. Installez le module "Pointeur HR"

### Configuration initiale
1. Créez les lieux de pointage (Présences > Configuration > Lieux de pointage)
2. Vérifiez les droits d'accès des utilisateurs
3. Configurez les paramètres par défaut si nécessaire

## Support technique
Pour toute question ou problème :
1. Consultez les messages d'erreur détaillés
2. Vérifiez le format de vos données d'import
3. Contactez le support technique si nécessaire

## Bonnes pratiques
- Vérifiez toujours vos données avant l'import
- Créez les correspondances avec précaution
- Utilisez les filtres pour un meilleur suivi
- Consultez régulièrement les statistiques
- Gardez vos correspondances à jour
