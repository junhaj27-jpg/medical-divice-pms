from functools import wraps
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import IntegrityError, OperationalError


def guarded(fn):
    """Rollback precedes conflict translation; a retry uses the same request key."""
    @wraps(fn)
    def call(*args,**kwargs):
        try: return fn(*args,**kwargs)
        except ObjectDoesNotExist:
            raise ValidationError('접근할 수 없거나 존재하지 않는 대상입니다.') from None
        except (ValueError,TypeError):
            raise ValidationError('입력 값의 형식을 확인하세요.') from None
        except IntegrityError:
            raise ValidationError('동시 요청 또는 중복 기록입니다. 같은 요청 키로 최신 결과를 확인하세요.') from None
        except OperationalError as exc:
            if any(word in str(exc).lower() for word in ('locked','deadlock','serialize')):
                raise ValidationError('동시 처리 중입니다. 같은 요청 키로 다시 요청하세요.') from None
            raise
    return call
