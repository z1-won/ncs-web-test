"""기존 파일 실행 명령을 위한 호환 진입점. 먼저 프로젝트의 web extra를 설치한다."""

from ncs_web.server import create_app, main

__all__ = ["create_app", "main"]

if __name__ == "__main__":
    main()
