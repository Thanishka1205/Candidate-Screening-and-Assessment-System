$(document).ready(function() {
    $('#tech_stack').select2({
        placeholder: "Select your tech stack",
        width: '100%'
    });

    function toggleExperienceFields() {
        const value = $('#has_experience').val();
        if (value === 'Yes') {
            $('#experience_fields').slideDown();
        } else {
            $('#experience_fields').slideUp();
        }
    }

    $('#has_experience').change(toggleExperienceFields);
    toggleExperienceFields();  // Initial check in case of prefilled data
}); 