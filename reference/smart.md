# Проверка здоровья накопителя (SMART)

Справочник к шагам, где перед установкой системы нужно решить, можно ли доверять диску.

## Столбцы вывода `smartctl -A`

```text
ID# ATTRIBUTE_NAME          FLAG     VALUE WORST THRESH TYPE      UPDATED  WHEN_FAILED RAW_VALUE
  5 Reallocated_Sector_Ct   0x0033   100   100   010    Pre-fail  Always       -       0
177 Wear_Leveling_Count     0x0013   087   087   000    Pre-fail  Always       -       142
```

| Столбец | Что в нём |
|---|---|
| `VALUE` | текущее нормализованное значение по шкале производителя (обычно 100, 200 или 253 у нового диска). Больше — лучше |
| `WORST` | худшее значение `VALUE` за всю жизнь диска |
| `THRESH` | порог: если `VALUE` опустится до него, атрибут считается отказавшим. `0` означает информационный атрибут |
| `TYPE` | `Pre-fail` — предвестник отказа; `Old_age` — признак выработки ресурса |
| `UPDATED` | `Always` — обновляется постоянно, `Offline` — только при самотестах |
| `WHEN_FAILED` | должен быть прочерк; `FAILING_NOW` или `In_the_past` — атрибут пересекал порог |
| `RAW_VALUE` | «сырой» счётчик: секторы, часы, циклы. Формат зависит от производителя |

Общее правило: **счётчики ошибок смотри в `RAW_VALUE`** (там реальное количество), **износ SSD — в `VALUE`** (там проценты оставшегося ресурса). Порогу `THRESH` полностью доверять не стоит: диски часто умирают раньше, чем `VALUE` до него доберётся.

У дисков Seagate `Raw_Read_Error_Rate` и `Seek_Error_Rate` показывают огромные числа — это закодированные служебные данные, а не количество ошибок.

## Команды

```bash
sudo apt install -y smartmontools

lsblk -o NAME,SIZE,MODEL,ROTA,TRAN   # ROTA=1 — HDD, ROTA=0 — SSD
sudo smartctl -i /dev/sdX            # модель, прошивка, поддержка SMART
sudo smartctl -H /dev/sdX            # общий вердикт
sudo smartctl -A /dev/sdX            # атрибуты
sudo smartctl -x /dev/sdX            # расширенный вывод, включая Device Statistics

sudo smartctl -t short /dev/sdX      # самотест, 1–2 минуты
sudo smartctl -l selftest /dev/sdX   # результат
```

`SMART overall-health` часто показывает `PASSED` почти до самой смерти диска, поэтому смотреть нужно атрибуты.

## HDD

| Атрибут | Что значит | Норма |
|---|---|---|
| `Reallocated_Sector_Ct` | сбойные секторы, заменённые резервными | 0 |
| `Current_Pending_Sector` | «подозрительные» секторы в очереди на переназначение | 0 |
| `Offline_Uncorrectable` | секторы, которые не удалось прочитать | 0 |
| `Reported_Uncorrect` | неисправимые ошибки чтения | 0 |
| `Power_On_Hours` | наработка | для справки |

Единичные переназначенные секторы терпимы, если их число не растёт: проверь ещё раз через несколько дней и сравни. Длинный тест (`smartctl -t long`) читает всю поверхность и находит то, что короткий пропускает.

## SSD

**Износ.** Атрибут называется по-разному: `Wear_Leveling_Count` (Samsung), `Media_Wearout_Indicator` (Intel), `Percent_Lifetime_Remain`, `SSD_Life_Left`. В `VALUE` — оставшийся ресурс в процентах. Надёжнее строка `Percentage Used Endurance Indicator` в разделе Device Statistics вывода `smartctl -x`: там показан израсходованный ресурс.

| Израсходовано | Вывод |
|---|---|
| до ~70% | всё хорошо |
| 70–90% | работать можно, бэкапы обязательны |
| больше 90% | лучше заменить |

**Объём записи.** `Total_LBAs_Written` (или `Host_Writes_GiB`). Значение в LBA умножь на 512 байт и сравни с TBW из спецификации модели.

**Ошибки — должны быть нулевыми:** `Reallocated_Sector_Ct`, `Reported_Uncorrect`, `Runtime_Bad_Block`, `Program_Fail_Count`, `Erase_Fail_Count`.

## Не про диск

`UDMA_CRC_Error_Count` указывает на проблему соединения (разъём, шлейф, кабель), а не на сам накопитель. Если счётчик растёт — переподключи диск.

## Подготовка подержанного SSD

Перед установкой системы имеет смысл пометить все ячейки как свободные:

```bash
lsblk -o NAME,SIZE,MODEL   # убедись, что это нужный диск
sudo blkdiscard /dev/sdX
```

**Команда необратимо уничтожает все данные.** Работает за секунды. Если discard не поддерживается, шаг можно пропустить.

## TRIM под шифрованием

После установки на SSD с LUKS проверь всю цепочку:

```bash
systemctl status fstrim.timer   # active (waiting)
cat /etc/crypttab               # в опциях должен быть discard
lsblk --discard                 # ненулевые DISC-GRAN и DISC-MAX
sudo fstrim -av
```

Если `discard` в `/etc/crypttab` нет, добавь его в колонку опций и выполни `sudo update-initramfs -u`. Компромисс: снаружи становится видно, какие блоки диска пустые (но не их содержимое).
