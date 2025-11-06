@echo off
set "APP_NAME=BlackNode-Clipper"
set "ENTRY_POINT=main.py"

echo Starting Nuitka build for %APP_NAME%...

REM تفعيل البيئة الافتراضية (افترض أنك في نفس المجلد)
call venv\Scripts\activate

REM [هام]: استخدام امر Nuitka مع تفعيل جميع الإضافات اللازمة 
REM - --plugin-enable=pyside6: لدعم واجهة PySide6
REM - --plugin-enable=numpy & opencv: لدمج مكتبة OpenCV بشكل صحيح
REM - --include-data-dir: لضم مجلد modules
REM - --include-data-file: لضم ملف config.yaml
REM - --windows-disable-console: لإخفاء نافذة الطرفية السوداء عند التشغيل
REM - --onefile: لإنشاء ملف تنفيذي واحد (اختياري، يمكنك حذفه واستخدام --standalone فقط)

python -m nuitka ^
    --standalone ^
    --onefile ^
    --output-dir=dist ^
    --mingw64 ^
    --windows-disable-console ^
    --follow-imports ^
    --plugin-enable=pyside6 ^
    --plugin-enable=numpy ^
    --plugin-enable=opencv ^
    --include-data-dir=modules=modules ^
    --include-data-file=config.yaml=config.yaml ^
    --output-filename=%APP_NAME% ^
    "%ENTRY_POINT%"

if %ERRORLEVEL% equ 0 (
    echo.
    echo -----------------------------------------------------------------------
    echo ✅ تم البناء بنجاح! الملف التنفيذي موجود في مجلد "dist".
    echo -----------------------------------------------------------------------
    
    REM === تعليمات هامة حول FFmpeg و VLC ===
    echo.
    echo ⚠️ خطوات هامة بعد البناء (يجب تنفيذها يدويا):
    
    REM بما أنك وضعت ffmpeg.exe و ffprobe.exe بجوار main.py، سيتم نقلهم الآن الى مجلد dist
    copy ffmpeg.exe dist\
    copy ffprobe.exe dist\
    echo 1. تم نسخ ffmpeg.exe و ffprobe.exe الى مجلد "dist".
    
    echo 2. يجب نسخ مكتبات VLC الإضافية (مثل plugins) يدوياً الى مجلد "dist" اذا لم يعمل تشغيل الفيديو.
    echo -----------------------------------------------------------------------

) else (
    echo.
    echo ❌ فشل عملية البناء! الرجاء مراجعة الأخطاء في الإخراج.
)

REM إلغاء تفعيل البيئة الافتراضية
deactivate

echo.
echo انتهى سكريبت البناء.
pause