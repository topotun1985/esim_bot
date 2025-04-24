import datetime
from typing import Optional, Union


def format_bytes(bytes_value: Union[int, float], decimal_places: int = 2) -> str:
    """
    Форматирует байты в человекочитаемый формат (KB, MB, GB)
    
    Args:
        bytes_value: Значение в байтах
        decimal_places: Количество знаков после запятой
        
    Returns:
        str: Отформатированная строка с единицей измерения
    """
    if bytes_value is None:
        return "0 B"
    
    bytes_value = float(bytes_value)
    
    if bytes_value == 0:
        return "0 B"
        
    size_names = ["B", "KB", "MB", "GB", "TB", "PB"]
    i = 0
    
    while bytes_value >= 1024 and i < len(size_names) - 1:
        bytes_value /= 1024.0
        i += 1
        
    return f"{bytes_value:.{decimal_places}f} {size_names[i]}"


def format_datetime(dt: Optional[datetime.datetime], 
                   format_str: str = "%d.%m.%Y %H:%M", 
                   language: str = "ru") -> str:
    """
    Форматирует дату и время в читаемый формат
    
    Args:
        dt: Объект datetime
        format_str: Строка формата (по умолчанию DD.MM.YYYY HH:MM)
        language: Код языка (ru или en)
        
    Returns:
        str: Отформатированная строка даты и времени или '-' если dt is None
    """
    if dt is None:
        return "-"
    
    # Преобразуем UTC в локальное время (UTC+3 для России)
    if language == "ru":
        local_dt = dt + datetime.timedelta(hours=3)
    else:
        local_dt = dt  # Для других языков оставляем UTC
        
    return local_dt.strftime(format_str)


def format_duration(days: Optional[int], language: str = "ru") -> str:
    """
    Форматирует длительность в днях в читаемый формат
    
    Args:
        days: Количество дней
        language: Код языка (ru или en)
        
    Returns:
        str: Отформатированная строка длительности
    """
    if days is None:
        return "-"
    
    if language == "ru":
        if days == 1:
            return "1 день"
        elif 2 <= days <= 4:
            return f"{days} дня"
        else:
            return f"{days} дней"
    else:  # en
        if days == 1:
            return "1 day"
        else:
            return f"{days} days"


def format_expiration_date(expired_time: Optional[datetime.datetime], language: str = "ru") -> str:
    """
    Форматирует дату истечения срока действия в читаемый формат с указанием оставшегося времени
    
    Args:
        expired_time: Дата истечения срока
        language: Код языка (ru или en)
        
    Returns:
        str: Отформатированная строка с датой и оставшимся временем
    """
    if expired_time is None:
        return "-"
    
    now = datetime.datetime.utcnow()
    
    # Если срок уже истек
    if now > expired_time:
        return format_datetime(expired_time, language=language) + (
            " (истек)" if language == "ru" else " (expired)"
        )
    
    # Рассчитываем оставшееся время
    remaining = expired_time - now
    days_remaining = remaining.days
    
    # Форматируем оставшееся время
    if language == "ru":
        if days_remaining == 0:
            hours_remaining = remaining.seconds // 3600
            if hours_remaining == 0:
                minutes_remaining = remaining.seconds // 60
                time_str = f"{minutes_remaining} мин."
            else:
                time_str = f"{hours_remaining} ч."
        elif days_remaining == 1:
            time_str = "1 день"
        elif 2 <= days_remaining <= 4:
            time_str = f"{days_remaining} дня"
        else:
            time_str = f"{days_remaining} дней"
    else:  # en
        if days_remaining == 0:
            hours_remaining = remaining.seconds // 3600
            if hours_remaining == 0:
                minutes_remaining = remaining.seconds // 60
                time_str = f"{minutes_remaining} min."
            else:
                time_str = f"{hours_remaining} hrs."
        elif days_remaining == 1:
            time_str = "1 day"
        else:
            time_str = f"{days_remaining} days"
    
    return format_datetime(expired_time, language=language) + (
        f" (осталось {time_str})" if language == "ru" else f" ({time_str} left)"
    )


def format_esim_status(status: Optional[str], language: str = "ru") -> str:
    """
    Форматирует статус eSIM в читаемый формат
    
    Args:
        status: Статус eSIM
        language: Код языка (ru или en)
        
    Returns:
        str: Отформатированная строка статуса
    """
    if status is None:
        return "-"
    
    status_map = {
        "ru": {
            "AVAILABLE": "✅ Доступна",
            "ACTIVATED": "✅ Активирована",
            "READY": "✅ Готова к активации",
            "GOT_RESOURCE": "✅ Активирована",
            "IN_USE": "✅ Активирована",
            "ENABLED": "✅ Активирована",
            "EXPIRED": "❌ Истек срок",
            "DEPLETED": "❌ Трафик исчерпан",
            "PENDING": "⏳ В обработке",
            "PROCESSING": "⏳ Активация",
            "INSTALLATION": "⏳ Установка",
            "FAILED": "❌ Ошибка",
            "CANCELED": "❌ Отменена",
            "CANCEL": "❌ Отменена",
            "RELEASED": "❌ Удалена"
        },
        "en": {
            "AVAILABLE": "✅ Available",
            "ACTIVATED": "✅ Activated",
            "READY": "✅ Ready to activate",
            "GOT_RESOURCE": "✅ Activated",
            "IN_USE": "✅ Activated",
            "ENABLED": "✅ Activated",
            "EXPIRED": "❌ Expired",
            "DEPLETED": "❌ Data depleted",
            "PENDING": "⏳ Pending",
            "PROCESSING": "⏳ Activating",
            "INSTALLATION": "⏳ Installing",
            "FAILED": "❌ Failed",
            "CANCELED": "❌ Canceled",
            "CANCEL": "❌ Canceled",
            "RELEASED": "❌ Removed"
        }
    }
    
    return status_map.get(language, {}).get(status.upper(), status)