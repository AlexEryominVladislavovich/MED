(function($) {
    'use strict';
    $(document).ready(function() {
        // Функция для добавления нового временного слота
        $('.add-time-slot').click(function(e) {
            e.preventDefault();
            var inline_group = $(this).closest('.inline-group');
            var total_forms = inline_group.find('[name$="-TOTAL_FORMS"]');
            var form_idx = parseInt(total_forms.val());
            
            // Клонируем пустую форму
            var empty_form = inline_group.find('.empty-form').clone(true);
            empty_form.removeClass('empty-form');
            
            // Обновляем индексы в форме
            empty_form.find(':input').each(function() {
                var name = $(this).attr('name');
                if(name) {
                    name = name.replace('__prefix__', form_idx);
                    $(this).attr('name', name);
                    $(this).attr('id', 'id_' + name);
                }
            });
            
            // Вставляем новую форму перед кнопкой добавления
            empty_form.insertBefore(inline_group.find('.add-row'));
            
            // Увеличиваем счетчик форм
            total_forms.val(form_idx + 1);
        });

        // Автоматическая установка длительности в зависимости от типа слота
        $(document).on('change', 'select[name$="-slot_type"]', function() {
            var duration_input = $(this).closest('tr').find('input[name$="-duration"]');
            if($(this).val() === 'consultation') {
                duration_input.val(15);
            } else if($(this).val() === 'treatment') {
                duration_input.val(40);
            }
        });

        // Валидация времени начала в зависимости от типа слота
        $(document).on('change', 'input[name$="-start_time"]', function() {
            var row = $(this).closest('tr');
            var slot_type = row.find('select[name$="-slot_type"]').val();
            var time = $(this).val();
            
            if(time) {
                var minutes = parseInt(time.split(':')[1]);
                if(slot_type === 'consultation' && minutes !== 40) {
                    alert('Консультация должна начинаться в XX:40');
                    $(this).val('');
                } else if(slot_type === 'treatment' && minutes !== 0) {
                    alert('Лечение должно начинаться в XX:00');
                    $(this).val('');
                }
            }
        });
    });
})(django.jQuery); 